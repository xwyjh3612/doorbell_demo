/* USB descriptors and passive diagnostic sample; no AT, activation or media. */
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_intr_alloc.h"
#include "esp_log.h"
#include "esp_timer.h"
#include <string.h>
#include "usb/usb_host.h"
#include "hal/usb_dwc_ll.h"
#include "usb_at_probe.h"

#if !CONFIG_IDF_TARGET_ESP32S3
#error "This wiring and diagnostic project require ESP32-S3"
#endif

static const char *TAG = "ML307_USB_ENUM";

/* S3-specific read-only register snapshot, including failed enumeration. */
static void report_port_change(void)
{
    static uint32_t last = UINT32_MAX;
    usb_dwc_hprt_reg_t port = {.val = USB_DWC_LL_GET_HW(0)->hprt_reg.val};
    const uint32_t state = port.prtconnsts | (port.prtena << 1) |
                           (port.prtrst << 2) | (port.prtpwr << 3) |
                           (port.prtspd << 4);
    if (state == last) {
        return;
    }
    last = state;
    ESP_LOGI(TAG, "PORT connected=%u enabled=%u reset=%u power=%u speed_code=%u line_code=%u",
             port.prtconnsts, port.prtena, port.prtrst, port.prtpwr,
             port.prtspd, port.prtlnsts);
    if (port.prtena && !port.prtrst) {
        ESP_LOGI(TAG, "PORT negotiated speed=%s",
                 port.prtspd == USB_DWC_SPEED_FULL ? "full" :
                 port.prtspd == USB_DWC_SPEED_LOW ? "low" : "other");
    }
}

typedef struct {
    uint8_t pending_address;
    usb_device_handle_t device;
    bool disconnected;
    usb_transfer_t *string_transfer;
    bool string_inflight;
    unsigned string_cursor;
    uint16_t language;
    bool diag_named;
    bool at_named;
    bool diag_attempted;
    bool diag_claimed;
    bool diag_inflight;
    bool diag_stopping;
    usb_transfer_t *diag_transfer;
    int64_t diag_started;
} probe_state_t;

static const uint8_t string_indices[] = {0, 5, 8, 11};

static void string_completed(usb_transfer_t *transfer)
{
    probe_state_t *state = transfer->context;
    state->string_inflight = false;
    const uint8_t index = string_indices[state->string_cursor - 1];
    const int header_size = sizeof(usb_setup_packet_t);
    const uint8_t *desc = transfer->data_buffer + header_size;
    int size = transfer->actual_num_bytes - header_size;
    if (transfer->status != USB_TRANSFER_STATUS_COMPLETED || size < 2 ||
        desc[1] != USB_B_DESCRIPTOR_TYPE_STRING || desc[0] > size || desc[0] < 2) {
        ESP_LOGW(TAG, "STRING index=%u unavailable status=%d bytes=%d", index,
                 transfer->status, transfer->actual_num_bytes);
        return;
    }
    size = desc[0];
    if (index == 0) {
        if (size >= 4) {
            state->language = desc[2] | (desc[3] << 8);
            ESP_LOGI(TAG, "STRING language=0x%04x", state->language);
        }
        return;
    }
    char label[128];
    unsigned used = 0;
    for (int i = 2; i + 1 < size && used < sizeof(label) - 1; i += 2) {
        label[used++] = desc[i + 1] == 0 && desc[i] >= 0x20 && desc[i] < 0x7f
                        ? desc[i] : '?';
    }
    label[used] = '\0';
    ESP_LOGI(TAG, "STRING index=%u label=%s", index, label);
    if (index == 8 && strcmp(label, "Mobile Diag Interface") == 0) {
        state->diag_named = true;
    }
    if (index == 11 && strcmp(label, "Mobile AT Interface") == 0) {
        state->at_named = true;
    }
}

static void diag_completed(usb_transfer_t *transfer)
{
    probe_state_t *state = transfer->context;
    state->diag_inflight = false;
    if (transfer->status == USB_TRANSFER_STATUS_COMPLETED) {
        char hex[129];
        const char digits[] = "0123456789abcdef";
        unsigned size = transfer->actual_num_bytes;
        if (size > 64) {
            size = 64;
        }
        for (unsigned i = 0; i < size; ++i) {
            hex[2 * i] = digits[transfer->data_buffer[i] >> 4];
            hex[2 * i + 1] = digits[transfer->data_buffer[i] & 15];
        }
        hex[2 * size] = '\0';
        ESP_LOGI(TAG, "DIAG_SAMPLE bytes=%u hex=%s", size, hex);
    } else {
        ESP_LOGI(TAG, "DIAG sample ended status=%d bytes=%d", transfer->status,
                 transfer->actual_num_bytes);
    }
}

/* Receive one packet, up to 64 bytes; never transmit vendor/AT commands. */
static void sample_diag(usb_host_client_handle_t client, probe_state_t *state)
{
    if (state->diag_claimed) {
        if ((state->disconnected || esp_timer_get_time() - state->diag_started > 45000000) &&
            state->diag_inflight && !state->diag_stopping) {
            state->diag_stopping = true;
            ESP_ERROR_CHECK(usb_host_endpoint_halt(state->device, 0x82));
            ESP_ERROR_CHECK(usb_host_endpoint_flush(state->device, 0x82));
            ESP_LOGI(TAG, "DIAG passive window ended; no diagnostic activation sent");
        }
        if (!state->diag_inflight) {
            ESP_ERROR_CHECK(usb_host_interface_release(client, state->device, 4));
            ESP_ERROR_CHECK(usb_host_transfer_free(state->diag_transfer));
            state->diag_transfer = NULL;
            state->diag_claimed = false;
        }
        return;
    }
    if (!state->device || state->disconnected || !state->diag_named ||
        state->string_inflight || state->string_cursor < sizeof(string_indices) ||
        state->diag_attempted) {
        return;
    }
    state->diag_attempted = true;
    const usb_device_desc_t *device_desc;
    const usb_config_desc_t *config_desc;
    if (usb_host_get_device_descriptor(state->device, &device_desc) != ESP_OK ||
        device_desc->idVendor != 0x2ecc || device_desc->idProduct != 0x3012 ||
        usb_host_get_active_config_descriptor(state->device, &config_desc) != ESP_OK) {
        return;
    }
    /* Require the actual interface/endpoint shape observed on this firmware. */
    const uint8_t *bytes = (const uint8_t *)config_desc;
    bool interface_matches = false, endpoint_matches = false;
    for (unsigned offset = 0; offset + 2 <= config_desc->wTotalLength;) {
        unsigned size = bytes[offset];
        if (size < 2 || offset + size > config_desc->wTotalLength) {
            return;
        }
        if (bytes[offset + 1] == USB_B_DESCRIPTOR_TYPE_INTERFACE && size >= 9) {
            interface_matches = bytes[offset + 2] == 4 && bytes[offset + 3] == 0 &&
                                bytes[offset + 5] == 0xff && bytes[offset + 8] == 8;
        } else if (interface_matches && bytes[offset + 1] == USB_B_DESCRIPTOR_TYPE_ENDPOINT && size >= 7) {
            endpoint_matches |= bytes[offset + 2] == 0x82 && (bytes[offset + 3] & 3) == 2 &&
                                bytes[offset + 4] == 64 && bytes[offset + 5] == 0;
        }
        offset += size;
    }
    if (!endpoint_matches) {
        ESP_LOGW(TAG, "DIAG endpoint shape changed; passive probe skipped");
        return;
    }
    esp_err_t err = usb_host_interface_claim(client, state->device, 4, 0);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "DIAG claim failed: %s", esp_err_to_name(err));
        return;
    }
    err = usb_host_transfer_alloc(64, 0, &state->diag_transfer);
    if (err != ESP_OK) {
        ESP_ERROR_CHECK(usb_host_interface_release(client, state->device, 4));
        ESP_LOGW(TAG, "DIAG transfer allocation failed: %s", esp_err_to_name(err));
        return;
    }
    state->diag_claimed = true;
    state->diag_stopping = false;
    state->diag_started = esp_timer_get_time();
    usb_transfer_t *transfer = state->diag_transfer;
    transfer->device_handle = state->device;
    transfer->bEndpointAddress = 0x82;
    transfer->num_bytes = 64;
    transfer->callback = diag_completed;
    transfer->context = state;
    state->diag_inflight = true;
    err = usb_host_transfer_submit(transfer);
    if (err != ESP_OK) {
        state->diag_inflight = false;
        ESP_LOGW(TAG, "DIAG IN request failed: %s", esp_err_to_name(err));
    } else {
        ESP_LOGI(TAG, "DIAG interface=4 IN=0x82 passive single-packet receive, 45-second window");
    }
}

static void request_next_string(usb_host_client_handle_t client, probe_state_t *state)
{
    if (!state->device || state->disconnected || state->string_inflight ||
        state->string_cursor >= sizeof(string_indices)) {
        return;
    }
    if (!state->string_transfer) {
        esp_err_t err = usb_host_transfer_alloc(264, 0, &state->string_transfer);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "String transfer allocation failed: %s", esp_err_to_name(err));
            state->string_cursor = sizeof(string_indices);
            return;
        }
    }
    usb_transfer_t *transfer = state->string_transfer;
    uint8_t index = string_indices[state->string_cursor++];
    USB_SETUP_PACKET_INIT_GET_STR_DESC((usb_setup_packet_t *)transfer->data_buffer,
                                      index, index ? state->language : 0, 255);
    transfer->num_bytes = 264; /* setup plus whole 64-byte endpoint packets */
    transfer->device_handle = state->device;
    transfer->bEndpointAddress = 0;
    transfer->callback = string_completed;
    transfer->context = state;
    state->string_inflight = true;
    esp_err_t err = usb_host_transfer_submit_control(client, transfer);
    if (err != ESP_OK) {
        state->string_inflight = false;
        ESP_LOGW(TAG, "String request index=%u failed: %s", index, esp_err_to_name(err));
    }
}

/* Executed by usb_host_client_handle_events in the main task. */
static void client_event(const usb_host_client_event_msg_t *event, void *arg)
{
    probe_state_t *state = arg;
    if (event->event == USB_HOST_CLIENT_EVENT_NEW_DEV) {
        state->pending_address = event->new_dev.address;
    } else if (event->event == USB_HOST_CLIENT_EVENT_DEV_GONE) {
        if (state->device == event->dev_gone.dev_hdl) {
            state->disconnected = true;
        }
    }
}

static void host_events(void *arg)
{
    (void)arg;
    for (;;) {
        uint32_t flags;
        ESP_ERROR_CHECK(usb_host_lib_handle_events(portMAX_DELAY, &flags));
    }
}

static void print_descriptors(usb_device_handle_t device)
{
    usb_device_info_t info;
    esp_err_t err = usb_host_device_info(device, &info);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Device info unavailable: %s", esp_err_to_name(err));
        return;
    }
    ESP_LOGI(TAG, "Connected: address=%u speed=%s configuration=%u",
             info.dev_addr, info.speed == USB_SPEED_FULL ? "full" : "other",
             info.bConfigurationValue);

    const usb_device_desc_t *device_desc;
    err = usb_host_get_device_descriptor(device, &device_desc);
    if (err == ESP_OK) {
        usb_print_device_descriptor(device_desc);
    } else {
        ESP_LOGW(TAG, "Device descriptor unavailable: %s", esp_err_to_name(err));
    }
    const usb_config_desc_t *config_desc;
    err = usb_host_get_active_config_descriptor(device, &config_desc);
    if (err == ESP_OK) {
        usb_print_config_descriptor(config_desc, NULL);
    } else {
        ESP_LOGW(TAG, "Configuration descriptor unavailable: %s", esp_err_to_name(err));
    }
    ESP_LOGI(TAG, "Enumeration captured; log/AT interfaces have not been opened");
}

void app_main(void)
{
    ESP_LOGI(TAG, "Standalone USB probe, UART0 console at 115200");
    ESP_LOGI(TAG, "USB D-=GPIO19, D+=GPIO20; UART17/18 not driven by this demo");
    const usb_host_config_t host_config = {
        .skip_phy_setup = false,
        .intr_flags = ESP_INTR_FLAG_LEVEL1,
    };
    ESP_ERROR_CHECK(usb_host_install(&host_config));

    probe_state_t state = {0};
    usb_host_client_handle_t client;
    const usb_host_client_config_t client_config = {
        .is_synchronous = false,
        .max_num_event_msg = 8,
        .async = {
            .client_event_callback = client_event,
            .callback_arg = &state,
        },
    };
    ESP_ERROR_CHECK(usb_host_client_register(&client_config, &client));
    if (xTaskCreate(host_events, "usb_host_events", 4096, NULL, 2, NULL) != pdPASS) {
        ESP_ERROR_CHECK(ESP_ERR_NO_MEM);
    }
    ESP_LOGI(TAG, "Waiting for module USB; no periodic descriptor logging");

    for (;;) {
        esp_err_t event_err = usb_host_client_handle_events(client, pdMS_TO_TICKS(50));
        if (event_err != ESP_OK && event_err != ESP_ERR_TIMEOUT) {
            ESP_ERROR_CHECK(event_err);
        }
        report_port_change();
        sample_diag(client, &state);
        usb_at_probe_poll(client, state.device, state.at_named && !state.string_inflight,
                          state.disconnected);
        if (state.disconnected && !state.string_inflight && !state.diag_claimed &&
            !usb_at_probe_busy()) {
            esp_err_t err = usb_host_device_close(client, state.device);
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "Close failed: %s", esp_err_to_name(err));
                ESP_ERROR_CHECK(err);
            }
            state.device = NULL;
            state.disconnected = false;
            state.string_cursor = 0;
            state.diag_named = false;
            state.at_named = false;
            state.diag_attempted = false;
            usb_at_probe_reset();
            ESP_LOGW(TAG, "USB disconnected; this alone does not identify a reset cause");
        }
        if (state.pending_address != 0) {
            uint8_t address = state.pending_address;
            state.pending_address = 0;
            if (state.device != NULL) {
                ESP_LOGW(TAG, "Only one directly connected device is supported");
                continue;
            }
            esp_err_t err = usb_host_device_open(client, address, &state.device);
            if (err != ESP_OK) {
                state.device = NULL;
                ESP_LOGW(TAG, "Open failed: %s", esp_err_to_name(err));
                continue;
            }
            print_descriptors(state.device);
            state.language = 0x0409;
            state.string_cursor = 0;
        }
        request_next_string(client, &state);
    }
}
