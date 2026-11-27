/* Observe normal/Dump USB enumeration alongside the unchanged UART transport.
 * No vendor commands, interface claims, bulk transfers or module resets.
 */
#include "ml307_usb_observer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_intr_alloc.h"
#include "esp_log.h"
#include "hal/usb_dwc_ll.h"
#include "usb/usb_host.h"

#if !CONFIG_IDF_TARGET_ESP32S3
#error "USB observation wiring requires ESP32-S3"
#endif
#if !CONFIG_ESP_CONSOLE_SECONDARY_NONE
#error "USB observation requires disabling the USB Serial/JTAG secondary console"
#endif

static const char *TAG = "ML307_USB_OBS";

typedef struct {
    uint8_t pending_address;
    usb_device_handle_t device;
    bool disconnected;
} observer_t;

/* Called in the observer task by usb_host_client_handle_events. */
static void client_event(const usb_host_client_event_msg_t *event, void *arg)
{
    observer_t *state = arg;
    if (event->event == USB_HOST_CLIENT_EVENT_NEW_DEV) {
        state->pending_address = event->new_dev.address;
    } else if (event->event == USB_HOST_CLIENT_EVENT_DEV_GONE &&
               event->dev_gone.dev_hdl == state->device) {
        state->disconnected = true;
    }
}

static void host_events(void *arg)
{
    (void)arg;
    for (;;) {
        uint32_t flags = 0;
        esp_err_t err = usb_host_lib_handle_events(portMAX_DELAY, &flags);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Host event error: %s", esp_err_to_name(err));
            vTaskDelay(pdMS_TO_TICKS(1000));
        }
    }
}

static void report_port_change(void)
{
    static uint32_t last = UINT32_MAX;
    usb_dwc_hprt_reg_t port = {.val = USB_DWC_LL_GET_HW(0)->hprt_reg.val};
    uint32_t state = port.prtconnsts | (port.prtena << 1) |
                     (port.prtrst << 2) | (port.prtpwr << 3) | (port.prtspd << 4);
    if (state != last) {
        last = state;
        ESP_LOGI(TAG, "PORT connected=%u enabled=%u reset=%u power=%u speed_code=%u",
                 port.prtconnsts, port.prtena, port.prtrst, port.prtpwr, port.prtspd);
    }
}

static void report_device(usb_device_handle_t device)
{
    const usb_device_desc_t *desc;
    esp_err_t err = usb_host_get_device_descriptor(device, &desc);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Device descriptor unavailable: %s", esp_err_to_name(err));
        return;
    }
    ESP_LOGI(TAG, "ENUM vid=%04x pid=%04x bcdDevice=%04x class=%02x",
             desc->idVendor, desc->idProduct, desc->bcdDevice, desc->bDeviceClass);
    if (desc->idVendor != 0x2ecc || desc->idProduct != 0x3012) {
        ESP_LOGW(TAG, "Device differs from normal 2ecc:3012; preserve fault scene, no automatic reset");
    }
    const usb_config_desc_t *config;
    err = usb_host_get_active_config_descriptor(device, &config);
    if (err == ESP_OK) {
        /* Cached standard descriptors, printed once per enumeration. */
        usb_print_config_descriptor(config, NULL);
    } else {
        ESP_LOGW(TAG, "Configuration descriptor unavailable: %s", esp_err_to_name(err));
    }
}

static void observer_task(void *arg)
{
    (void)arg;
    const usb_host_config_t config = {
        .skip_phy_setup = false,
        .intr_flags = ESP_INTR_FLAG_LEVEL1,
    };
    esp_err_t err = usb_host_install(&config);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "USB observation unavailable: %s; UART voice continues", esp_err_to_name(err));
        vTaskDelete(NULL);
        return;
    }
    observer_t state = {0};
    usb_host_client_handle_t client;
    const usb_host_client_config_t client_config = {
        .is_synchronous = false,
        .max_num_event_msg = 8,
        .async = {.client_event_callback = client_event, .callback_arg = &state},
    };
    err = usb_host_client_register(&client_config, &client);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "USB client unavailable: %s; UART voice continues", esp_err_to_name(err));
        usb_host_uninstall();
        vTaskDelete(NULL);
        return;
    }
    if (xTaskCreate(host_events, "usb_obs_host", 4096, NULL, 2, NULL) != pdPASS) {
        ESP_LOGW(TAG, "USB host task allocation failed; UART voice continues");
        usb_host_client_deregister(client);
        usb_host_uninstall();
        vTaskDelete(NULL);
        return;
    }
    ESP_LOGI(TAG, "Debug observer ready D-=GPIO19 D+=GPIO20; UART17/18 remains call transport");
    for (;;) {
        err = usb_host_client_handle_events(client, pdMS_TO_TICKS(100));
        if (err != ESP_OK && err != ESP_ERR_TIMEOUT) {
            ESP_LOGW(TAG, "Client event error: %s", esp_err_to_name(err));
            vTaskDelay(pdMS_TO_TICKS(1000));
        }
        report_port_change();
        if (state.disconnected) {
            err = usb_host_device_close(client, state.device);
            if (err != ESP_OK) {
                ESP_LOGW(TAG, "USB device close failed: %s", esp_err_to_name(err));
                vTaskDelay(pdMS_TO_TICKS(1000));
                continue;
            }
            state.device = NULL;
            state.disconnected = false;
            ESP_LOGW(TAG, "USB device gone; disconnect alone does not identify reset cause");
        }
        if (state.pending_address) {
            uint8_t address = state.pending_address;
            state.pending_address = 0;
            if (state.device) {
                ESP_LOGW(TAG, "Additional device ignored; single-module observer");
                continue;
            }
            err = usb_host_device_open(client, address, &state.device);
            if (err != ESP_OK) {
                state.device = NULL;
                ESP_LOGW(TAG, "USB device open failed: %s", esp_err_to_name(err));
                continue;
            }
            report_device(state.device);
        }
    }
}

esp_err_t ml307_usb_observer_start(void)
{
    return xTaskCreate(observer_task, "usb_observer", 4096, NULL, 2, NULL) == pdPASS
           ? ESP_OK : ESP_ERR_NO_MEM;
}
