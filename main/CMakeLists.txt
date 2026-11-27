set(voice_sources "main.cpp" "board.c" "media_sys.c" "webrtc_mqtt.c" "mqtt_signaling.cpp" "app_config.c"
 "network_4g.cpp" "ml307_udp_socket.cc" "door_bell_audio.c" "otaupgrade.cpp" "latest_pcm_audio_src.cpp")
if(CONFIG_VOICE_RADAR_ENABLE)
    list(APPEND voice_sources "radar_presence.c" "radar_telemetry.cpp")
endif()
if(CONFIG_VOICE_POWER_MONITOR_ENABLE)
    list(APPEND voice_sources "power_monitor.cpp")
endif()
if(CONFIG_VOICE_STATUS_INDICATOR_ENABLE)
    list(APPEND voice_sources "status_indicator.cpp")
endif()
if(CONFIG_VOICE_ML307_USB_OBSERVER)
    list(APPEND voice_sources "ml307_usb_observer.c")
endif()
idf_component_register(SRCS ${voice_sources}
                       EMBED_TXTFILES "ring.aac" "outgoing.aac" "open.aac" "join.aac"
                       INCLUDE_DIRS ".")
