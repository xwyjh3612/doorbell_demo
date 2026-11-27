#include "usb_at_probe.h"
#include "esp_log.h"
#include "esp_timer.h"
#include <string.h>
#include <stdio.h>
#include <assert.h>
#include "sdkconfig.h"

static const char *TAG = "ML307_USB_AT";
static const char *queries[] = {
    "AT\r\n", "AT+CGMR\r\n", "AT+MDUMPCFG?\r\n",
#if CONFIG_ML307C_PROBE_ENABLE_DUMP_SAVE
    "AT+MDUMPCFG=1\r\n", "AT+MDUMPCFG?\r\n",
#endif
};
static bool dump_enable_run_completed;
static struct {
    bool attempted, claimed, rx_pending, tx_pending, stopping, done;
    unsigned query;
    int64_t sent_at;
    usb_transfer_t *rx, *tx;
    char response[1024];
    unsigned used;
} probe;

static void rx_complete(usb_transfer_t *transfer)
{
    probe.rx_pending = false;
    if (transfer->status != USB_TRANSFER_STATUS_COMPLETED) {
        if (!probe.stopping) {
            ESP_LOGW(TAG, "IN failed status=%d", transfer->status);
            probe.done = true;
        }
        return;
    }
    unsigned size = transfer->actual_num_bytes;
    if (size > sizeof(probe.response) - 1 - probe.used) {
        size = sizeof(probe.response) - 1 - probe.used;
    }
    memcpy(probe.response + probe.used, transfer->data_buffer, size);
    probe.used += size;
    probe.response[probe.used] = '\0';
    if (strstr(probe.response, "\r\nOK\r\n") ||
        strstr(probe.response, "\r\nERROR\r\n") ||
        strstr(probe.response, "+CME ERROR:")) {
        probe.done = true;
    }
}

static void tx_complete(usb_transfer_t *transfer)
{
    probe.tx_pending = false;
    if (transfer->status != USB_TRANSFER_STATUS_COMPLETED) {
        ESP_LOGW(TAG, "OUT failed status=%d", transfer->status);
        probe.done = true;
    }
}

static void submit_rx(usb_device_handle_t device)
{
    if (probe.rx_pending || probe.stopping) {
        return;
    }
    probe.rx->device_handle = device;
    probe.rx->bEndpointAddress = 0x81;
    probe.rx->num_bytes = 64;
    probe.rx->callback = rx_complete;
    esp_err_t err = usb_host_transfer_submit(probe.rx);
    probe.rx_pending = err == ESP_OK;
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "IN submission failed: %s", esp_err_to_name(err));
        probe.done = true;
    }
}

static void send_query(usb_device_handle_t device)
{
    probe.used = 0;
    probe.response[0] = '\0';
    probe.done = false;
    probe.sent_at = esp_timer_get_time();
    const char *query = queries[probe.query];
    size_t size = strlen(query);
    memcpy(probe.tx->data_buffer, query, size);
    probe.tx->device_handle = device;
    probe.tx->bEndpointAddress = 0x0a;
    probe.tx->num_bytes = size;
    probe.tx->callback = tx_complete;
    submit_rx(device);
    esp_err_t err = usb_host_transfer_submit(probe.tx);
    probe.tx_pending = err == ESP_OK;
    ESP_LOGI(TAG, "AT step=%u interface=2 OUT=0x0a", probe.query);
#if CONFIG_ML307C_PROBE_ENABLE_DUMP_SAVE
    if (probe.query == 3) {
        ESP_LOGI(TAG, "Applying documented crash-save setting: AT+MDUMPCFG=1");
    }
#endif
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "OUT submission failed: %s", esp_err_to_name(err));
        probe.done = true;
    }
}

/* Only emit response lines from these fixed, non-credential queries. */
static void report_response(void)
{
    ESP_LOGI(TAG, "Query=%u bytes=%u timeout=%u", probe.query, probe.used,
             !probe.done);
    char copy[1024];
    memcpy(copy, probe.response, probe.used + 1);
    char *context = NULL;
    for (char *line = strtok_r(copy, "\r\n", &context); line;
         line = strtok_r(NULL, "\r\n", &context)) {
        if (!strcmp(line, "OK") || !strcmp(line, "ERROR") ||
            !strncmp(line, "+CME ERROR:", 11) || !strncmp(line, "+MDUMPCFG:", 10) ||
            !strncmp(line, "ML307C", 6) || !strncmp(line, "+CGMR:", 6)) {
            ESP_LOGI(TAG, "RESPONSE %s", line);
        }
    }
}

bool usb_at_probe_busy(void)
{
    return probe.claimed;
}

void usb_at_probe_reset(void)
{
    assert(!probe.claimed);
    memset(&probe, 0, sizeof(probe));
}

void usb_at_probe_poll(usb_host_client_handle_t client, usb_device_handle_t device,
                       bool names_confirmed, bool disconnected)
{
    if (probe.claimed) {
        if (disconnected) {
            probe.stopping = true;
        }
        if (probe.stopping) {
            if (probe.rx_pending) {
                ESP_ERROR_CHECK(usb_host_endpoint_halt(device, 0x81));
                ESP_ERROR_CHECK(usb_host_endpoint_flush(device, 0x81));
                return;
            }
            if (probe.tx_pending) {
                ESP_ERROR_CHECK(usb_host_endpoint_halt(device, 0x0a));
                ESP_ERROR_CHECK(usb_host_endpoint_flush(device, 0x0a));
                return;
            }
            ESP_ERROR_CHECK(usb_host_interface_release(client, device, 2));
            ESP_ERROR_CHECK(usb_host_transfer_free(probe.rx));
            ESP_ERROR_CHECK(usb_host_transfer_free(probe.tx));
            probe.rx = probe.tx = NULL;
            probe.claimed = false;
            ESP_LOGI(TAG, "USB AT probe finished; interface released");
            return;
        }
        if (!probe.tx_pending && (probe.done || esp_timer_get_time() - probe.sent_at > 5000000)) {
            report_response();
            bool ok = probe.done && strstr(probe.response, "\r\nOK\r\n") &&
                      !strstr(probe.response, "ERROR");
            if (!ok || (probe.query == 1 && !strstr(probe.response, "ML307C-DL-CN-MBRH1S00"))) {
                ESP_LOGW(TAG, "AT step failed or module identity differs; sequence stopped");
                probe.stopping = true;
                return;
            }
#if CONFIG_ML307C_PROBE_ENABLE_DUMP_SAVE
            if (probe.query == 2 && !strstr(probe.response, "+MDUMPCFG:")) {
                ESP_LOGW(TAG, "Dump status missing; configuration sequence stopped");
                probe.stopping = true;
                return;
            }
            if (probe.query == 4) {
                dump_enable_run_completed = true;
                if (strstr(probe.response, "+MDUMPCFG: 1\r\n")) {
                    ESP_LOGI(TAG, "DUMP_SAVE verified enabled=1; waiting for actual failure");
                } else {
                    ESP_LOGW(TAG, "DUMP_SAVE readback did not verify enabled=1");
                }
            }
#endif
            if (++probe.query == sizeof(queries) / sizeof(queries[0])) {
                probe.stopping = true;
            } else {
                send_query(device);
            }
        } else {
            submit_rx(device);
        }
        return;
    }
    if (probe.attempted || dump_enable_run_completed || !device || disconnected || !names_confirmed) {
        return;
    }
    probe.attempted = true;
    const usb_device_desc_t *desc;
    if (usb_host_get_device_descriptor(device, &desc) != ESP_OK ||
        desc->idVendor != 0x2ecc || desc->idProduct != 0x3012) {
        return;
    }
    const usb_config_desc_t *config;
    if (usb_host_get_active_config_descriptor(device, &config) != ESP_OK) {
        return;
    }
    const uint8_t *bytes = (const uint8_t *)config;
    bool match = false, in_found = false, out_found = false;
    for (unsigned offset = 0; offset + 2 <= config->wTotalLength;) {
        unsigned size = bytes[offset];
        if (size < 2 || offset + size > config->wTotalLength) {
            return;
        }
        if (bytes[offset + 1] == USB_B_DESCRIPTOR_TYPE_INTERFACE && size >= 9) {
            match = bytes[offset + 2] == 2 && bytes[offset + 3] == 0 &&
                    bytes[offset + 5] == 0xff && bytes[offset + 8] == 11;
        } else if (match && bytes[offset + 1] == USB_B_DESCRIPTOR_TYPE_ENDPOINT && size >= 7 &&
                   (bytes[offset + 3] & 3) == 2 && bytes[offset + 4] == 64 && bytes[offset + 5] == 0) {
            in_found |= bytes[offset + 2] == 0x81;
            out_found |= bytes[offset + 2] == 0x0a;
        }
        offset += size;
    }
    if (!in_found || !out_found) {
        ESP_LOGW(TAG, "AT endpoint layout changed; probe skipped");
        return;
    }
    esp_err_t err = usb_host_interface_claim(client, device, 2, 0);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "AT interface claim failed: %s", esp_err_to_name(err));
        return;
    }
    probe.claimed = true;
    err = usb_host_transfer_alloc(64, 0, &probe.rx);
    if (err == ESP_OK) {
        err = usb_host_transfer_alloc(64, 0, &probe.tx);
    }
    if (err != ESP_OK) {
        probe.stopping = true;
        ESP_LOGW(TAG, "AT allocation failed: %s", esp_err_to_name(err));
        return;
    }
    send_query(device);
}
