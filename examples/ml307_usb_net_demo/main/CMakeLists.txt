idf_component_register(SRCS "usb_network.c" INCLUDE_DIRS "."
    REQUIRES esp_netif esp_event esp_timer esp_driver_uart esp_driver_gpio lwip iot_eth iot_usbh_cdc iot_usbh_rndis iot_usbh_ecm)
