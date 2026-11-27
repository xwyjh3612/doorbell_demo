#pragma once
#include "FreeRTOS.h"
#include <thread>
#include <vector>
inline bool host_task_failure = false;
inline std::vector<std::thread> host_tasks;
inline int xTaskCreatePinnedToCore(void (*fn)(void *), const char *, int, void *arg, int, void *, int) {
    if (host_task_failure) return 0;
    host_tasks.emplace_back([=] { fn(arg); });
    return pdPASS;
}
inline void vTaskDelay(TickType_t ticks) { std::this_thread::sleep_for(std::chrono::milliseconds(ticks)); }
inline void vTaskDelete(void *) {}
inline void host_join_tasks() { for (auto &t : host_tasks) t.join(); host_tasks.clear(); }
