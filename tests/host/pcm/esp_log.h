#pragma once
#include <cstdio>
#define ESP_LOGI(tag, ...) do { (void)(tag); } while (0)
#define ESP_LOGE(tag, ...) do { (void)(tag); std::fprintf(stderr, __VA_ARGS__); std::fputc('\n', stderr); } while (0)
