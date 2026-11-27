#pragma once

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Debug build only: USB enumeration, no AT/diagnostic OUT or media traffic. */
esp_err_t ml307_usb_observer_start(void);

#ifdef __cplusplus
}
#endif
