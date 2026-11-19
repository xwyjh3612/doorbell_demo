idf_component_register(SRCS "radar_gpio5_demo.c"
                       INCLUDE_DIRS "."
                       REQUIRES esp_driver_uart esp_driver_gpio console esp_timer)
