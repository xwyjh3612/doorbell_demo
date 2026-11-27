#pragma once
#include "FreeRTOS.h"
#include <mutex>
#include <condition_variable>
#include <chrono>
struct HostSemaphore {
    std::mutex mutex;
    std::condition_variable changed;
    bool available;
    explicit HostSemaphore(bool initial) : available(initial) {}
};
using SemaphoreHandle_t = HostSemaphore *;
inline SemaphoreHandle_t xSemaphoreCreateMutex() { return new HostSemaphore(true); }
inline SemaphoreHandle_t xSemaphoreCreateBinary() { return new HostSemaphore(false); }
inline int xSemaphoreTake(SemaphoreHandle_t sem, TickType_t ticks) {
    std::unique_lock<std::mutex> lock(sem->mutex);
    auto ready = [&] { return sem->available; };
    if (ticks == portMAX_DELAY) sem->changed.wait(lock, ready);
    else if (!sem->changed.wait_for(lock, std::chrono::milliseconds(ticks), ready)) return 0;
    sem->available = false;
    return pdTRUE;
}
inline int xSemaphoreGive(SemaphoreHandle_t sem) {
    { std::lock_guard<std::mutex> lock(sem->mutex); sem->available = true; }
    sem->changed.notify_one();
    return pdTRUE;
}
inline void vSemaphoreDelete(SemaphoreHandle_t sem) { delete sem; }
