#include "network_4g.h"
#include <cstdio>
#include <cstring>
#include "esp_netif.h"
#include "esp_event.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "iot_eth.h"
#include "iot_eth_netif_glue.h"
#include "iot_usbh_cdc.h"
#include "iot_usbh_rndis.h"
#include "iot_usbh_ecm.h"

static EventGroupHandle_t usb_events;
static esp_netif_t *usb_interface;
static const int USB_READY=BIT0;

static void changed(void*,esp_event_base_t base,int32_t id,void*)
{
    if(base==IP_EVENT && id==IP_EVENT_ETH_GOT_IP){
        esp_netif_set_default_netif(usb_interface);xEventGroupSetBits(usb_events,USB_READY);
        ESP_LOGI("VOICE_USB_LINK","USB IP ready");
    }else if((base==IOT_ETH_EVENT && id==IOT_ETH_EVENT_DISCONNECTED)||
             (base==IP_EVENT && id==IP_EVENT_ETH_LOST_IP)){
        xEventGroupClearBits(usb_events,USB_READY);ESP_LOGW("VOICE_USB_LINK","USB network lost");
    }
}

extern "C" bool voice_usb_start()
{
    auto *modem=Network4g::GetModemInstance();if(!modem)return false;
    auto uart=modem->GetAtUart();
    // Profile never switches persistent USB mode or resets modem. Configure
    // RNDIS/ECM using the independent probe before running call comparisons.
    if(!uart->SendCommand("AT+MDIALUPCFG=\"mode\"",1000))return false;
    auto reply=uart->GetResponse();int mode=-1;
    auto at=reply.find("+MDIALUPCFG:");
    if(at!=std::string::npos)sscanf(reply.c_str()+at,"+MDIALUPCFG: \"mode\",%d",&mode);
#ifdef CONFIG_VOICE_TEST_ECM
    const int desired=1;
#else
    const int desired=0;
#endif
    if(mode!=desired){ESP_LOGE("VOICE_USB_LINK","USB mode=%d required=%d; no reset",mode,desired);return false;}
    ESP_ERROR_CHECK(esp_netif_init());
    esp_err_t event_ret=esp_event_loop_create_default();
    if(event_ret!=ESP_OK && event_ret!=ESP_ERR_INVALID_STATE)return false;
    usb_events=xEventGroupCreate();if(!usb_events)return false;
    ESP_ERROR_CHECK(esp_event_handler_register(IOT_ETH_EVENT,ESP_EVENT_ANY_ID,changed,nullptr));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT,IP_EVENT_ETH_GOT_IP,changed,nullptr));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT,IP_EVENT_ETH_LOST_IP,changed,nullptr));
    usbh_cdc_driver_config_t cdc={};cdc.task_stack_size=4096;cdc.task_priority=20;cdc.task_coreid=0;
    ESP_ERROR_CHECK(usbh_cdc_driver_install(&cdc));
    static const usb_device_match_id_t match[]={
        {.match_flags=USB_DEVICE_ID_MATCH_VID_PID,.idVendor=0x2ecc,.idProduct=0x3012},{}};
    iot_eth_driver_t *driver=nullptr;
#ifdef CONFIG_VOICE_TEST_ECM
    iot_usbh_ecm_config_t usb_cfg={};usb_cfg.match_id_list=match;
    ESP_ERROR_CHECK(iot_eth_new_usb_ecm(&usb_cfg,&driver));
#else
    iot_usbh_rndis_config_t usb_cfg={};usb_cfg.match_id_list=match;
    ESP_ERROR_CHECK(iot_eth_new_usb_rndis(&usb_cfg,&driver));
#endif
    iot_eth_config_t eth_cfg={};eth_cfg.driver=driver;iot_eth_handle_t eth=nullptr;
    ESP_ERROR_CHECK(iot_eth_install(&eth_cfg,&eth));
    esp_netif_inherent_config_t base=ESP_NETIF_INHERENT_DEFAULT_ETH();
    base.if_key="VOICE_USB";base.if_desc="Voice USB transport";
    esp_netif_config_t cfg={};cfg.base=&base;cfg.stack=ESP_NETIF_NETSTACK_DEFAULT_ETH;
    usb_interface=esp_netif_new(&cfg);if(!usb_interface)return false;
    auto glue=iot_eth_new_netif_glue(eth);if(!glue)return false;
    ESP_ERROR_CHECK(esp_netif_attach(usb_interface,glue));ESP_ERROR_CHECK(iot_eth_start(eth));
    if(!uart->SendCommand("AT+MDIALUP=1,1",3000))return false;
    auto bits=xEventGroupWaitBits(usb_events,USB_READY,pdFALSE,pdTRUE,pdMS_TO_TICKS(45000));
    return (bits&USB_READY)!=0;
}

extern "C" bool voice_usb_local_address(unsigned char *bytes)
{
    if(!usb_interface)return false;
    esp_netif_ip_info_t info={};
    if(esp_netif_get_ip_info(usb_interface,&info)!=ESP_OK || !info.ip.addr)return false;
    memcpy(bytes,&info.ip.addr,4);return true;
}
