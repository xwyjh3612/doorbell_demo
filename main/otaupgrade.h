#pragma once

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define FIRMWARE_VERSION 2

void ota_start_upgrade(const char* url, const char* md5);
bool ota_is_in_progress(void);

#ifdef __cplusplus
}
#endif
