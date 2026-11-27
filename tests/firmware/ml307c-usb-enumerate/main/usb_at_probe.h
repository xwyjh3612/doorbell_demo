#pragma once
#include "usb/usb_host.h"

/* Queries, with optional documented crash-save enable on known 2ECC:3012. */
void usb_at_probe_poll(usb_host_client_handle_t client, usb_device_handle_t device,
                       bool names_confirmed, bool disconnected);
bool usb_at_probe_busy(void);
void usb_at_probe_reset(void);
