/* Independent link probe using Espressif iot_usbh_rndis / iot_usbh_ecm.
 * Not a voice firmware or a complete call test. No raw AT/media/credential logs.
 */
#include <stdbool.h>
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <netdb.h>
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "driver/gpio.h"
#include "esp_err.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "iot_eth.h"
#include "iot_eth_netif_glue.h"
#include "iot_usbh_cdc.h"
#include "iot_usbh_rndis.h"
#include "iot_usbh_ecm.h"

static const char *TAG="USB_LINK_TEST";
static EventGroupHandle_t events;
static esp_netif_t *netif;
static unsigned links, losses, ips;
static const int GOT_IP=BIT0;
static const uart_port_t AT_UART=UART_NUM_1;
#ifdef CONFIG_VOICE_TEST_ECM
#define TEST_ECM 1
#else
#define TEST_ECM 0
#endif

/* Single owner AT task. USB IP traffic never waits for this command state. */
static bool at_command(const char *cmd, char *out, size_t capacity, int wait_ms)
{
    /* Read/flush old URCs before command; no dump of their contents. */
    uart_flush_input(AT_UART);
    size_t length=strlen(cmd);
    if (uart_write_bytes(AT_UART,cmd,length)!=(int)length ||
        uart_write_bytes(AT_UART,"\r\n",2)!=2) return false;
    size_t used=0; out[0]=0;
    int64_t end=esp_timer_get_time()+(int64_t)wait_ms*1000;
    while(esp_timer_get_time()<end){
        char buf[256]; int n=uart_read_bytes(AT_UART,buf,sizeof(buf),pdMS_TO_TICKS(20));
        if(n<=0)continue;
        size_t take=(size_t)n;
        if(take>capacity-used-1)take=capacity-used-1;
        memcpy(out+used,buf,take);used+=take;out[used]=0;
        if(strstr(out,"\r\nOK\r\n"))return true;
        if(strstr(out,"ERROR"))return false;
        if(used==capacity-1)return false;
    }
    return false;
}

static void at_setup(void *arg)
{
    char response[2048];
    bool ready=false;
    for(int retry=0;retry<30;retry++){
        if(at_command("AT",response,sizeof(response),500)){ready=true;break;}
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
    if(!ready){ESP_LOGE(TAG,"AT not responsive; no reset attempted");vTaskDelete(NULL);return;}
    if(!at_command("ATE0",response,sizeof(response),1000))goto failed;
    if(at_command("AT+CGMR",response,sizeof(response),1000)){
        /* Only print known module version token, no IMEI/ICCID/APN. */
        char *version=strstr(response,"ML307R-");
        if(version){char *end=strpbrk(version,"\r\n");if(end)*end=0;ESP_LOGI(TAG,"version=%.96s",version);}
    }
    if(!at_command("AT+MDIALUPCFG=\"mode\"",response,sizeof(response),1000))goto failed;
    int mode=-1;
    char *line=strstr(response,"+MDIALUPCFG:");
    if(line)sscanf(line,"+MDIALUPCFG: \"mode\",%d",&mode);
    int desired=TEST_ECM?1:0;
    ESP_LOGI(TAG,"usb_mode=%d target=%d",mode,desired);
    if(mode!=desired){
#if CONFIG_VOICE_TEST_AUTO_MODE_CHANGE
        char cmd[80];snprintf(cmd,sizeof(cmd),"AT+MDIALUPCFG=\"mode\",%d",desired);
        if(!at_command(cmd,response,sizeof(response),1000))goto failed;
        ESP_LOGW(TAG,"Persistent USB mode configured; one authorized modem reboot");
        at_command("AT+MREBOOT=0",response,sizeof(response),1000);
        vTaskDelay(pdMS_TO_TICKS(10000));
        if(!at_command("AT",response,sizeof(response),1000))goto failed;
        if(!at_command("ATE0",response,sizeof(response),1000))goto failed;
#else
        ESP_LOGE(TAG,"Mode differs; default build preserves configuration. Rebuild explicit test profile.");
        vTaskDelete(NULL);return;
#endif
    }
    const char *apn=CONFIG_VOICE_TEST_APN;
    if(*apn){
        if(strpbrk(apn,"\"\r\n")||strlen(apn)>90)goto failed;
        char cmd[160];snprintf(cmd,sizeof(cmd),"AT+CGDCONT=1,\"IPV4V6\",\"%s\"",apn);
        if(!at_command(cmd,response,sizeof(response),1000))goto failed;
    }
    /* Vendor dial manual: CID 1. AT controls setup only, not UDP packets. */
    for(int retry=0;retry<3;retry++){
        bool ok=at_command("AT+MDIALUP=1,1",response,sizeof(response),3000);
        ESP_LOGI(TAG,"dial_command accepted=%d attempt=%d",ok,retry+1);
        if(ok){vTaskDelete(NULL);return;}
        vTaskDelay(pdMS_TO_TICKS(5000));
    }
failed:
    ESP_LOGE(TAG,"AT setup failed; no repeating reset or raw command dump");
    vTaskDelete(NULL);
}

static void network_event(void *arg,esp_event_base_t base,int32_t id,void *data)
{
    if(base==IOT_ETH_EVENT){
        if(id==IOT_ETH_EVENT_CONNECTED){links++;ESP_LOGI(TAG,"usb_link_up count=%u",links);}
        if(id==IOT_ETH_EVENT_DISCONNECTED){losses++;xEventGroupClearBits(events,GOT_IP);ESP_LOGW(TAG,"usb_link_down count=%u",losses);}
    }else if(base==IP_EVENT && id==IP_EVENT_ETH_GOT_IP){
        ips++;esp_netif_set_default_netif(netif);xEventGroupSetBits(events,GOT_IP);
        ESP_LOGI(TAG,"ip_ready count=%u transport=%s",ips,TEST_ECM?"ECM":"RNDIS");
    }else if(base==IP_EVENT && id==IP_EVENT_ETH_LOST_IP){
        xEventGroupClearBits(events,GOT_IP);ESP_LOGW(TAG,"ip_lost");
    }
}

/* Read-only bounded TCP connectivity check; no speed test/large download. */
static void connectivity(void *arg)
{
    unsigned checks=0,dns_failures=0,tcp_failures=0;
    while(1){
        xEventGroupWaitBits(events,GOT_IP,pdFALSE,pdTRUE,portMAX_DELAY);
        struct addrinfo hint={.ai_family=AF_INET,.ai_socktype=SOCK_STREAM},*answer=NULL;
        int64_t start=esp_timer_get_time();
        int err=getaddrinfo("voice.2811.top","443",&hint,&answer);
        int result=-1;
        if(!err && answer){
            int s=socket(answer->ai_family,answer->ai_socktype,answer->ai_protocol);
            if(s>=0){
                int flags=fcntl(s,F_GETFL,0);fcntl(s,F_SETFL,flags|O_NONBLOCK);
                result=connect(s,answer->ai_addr,answer->ai_addrlen);
                if(result<0 && errno==EINPROGRESS){
                    fd_set writes;FD_ZERO(&writes);FD_SET(s,&writes);
                    struct timeval timeout={.tv_sec=3};
                    if(select(s+1,NULL,&writes,NULL,&timeout)>0){
                        int socket_error=-1;socklen_t length=sizeof(socket_error);
                        if(getsockopt(s,SOL_SOCKET,SO_ERROR,&socket_error,&length)==0 && socket_error==0)result=0;
                    }
                }
                close(s);
            }
            freeaddrinfo(answer);
            if(result)tcp_failures++;
        }else {if(answer)freeaddrinfo(answer);dns_failures++;}
        checks++;
        ESP_LOGI(TAG,"check=%u dns_ok=%d tcp443_ok=%d elapsed_ms=%lld dns_fail=%u tcp_fail=%u links=%u losses=%u heap=%lu",
            checks,!err,!err && !result,(long long)((esp_timer_get_time()-start)/1000),dns_failures,tcp_failures,links,losses,
            (unsigned long)esp_get_free_heap_size());
        vTaskDelay(pdMS_TO_TICKS(300000));
    }
}

void app_main(void)
{
    ESP_LOGI(TAG,"Independent USB network demo; NOT voice-call acceptance firmware");
    ESP_ERROR_CHECK(esp_netif_init());ESP_ERROR_CHECK(esp_event_loop_create_default());
    events=xEventGroupCreate();assert(events);
    uart_config_t uart_cfg={.baud_rate=CONFIG_VOICE_TEST_UART_BAUD,.data_bits=UART_DATA_8_BITS,
        .parity=UART_PARITY_DISABLE,.stop_bits=UART_STOP_BITS_1,.flow_ctrl=UART_HW_FLOWCTRL_DISABLE,
        .source_clk=UART_SCLK_DEFAULT};
    ESP_ERROR_CHECK(uart_driver_install(AT_UART,4096,2048,0,NULL,0));
    ESP_ERROR_CHECK(uart_param_config(AT_UART,&uart_cfg));
    ESP_ERROR_CHECK(uart_set_pin(AT_UART,17,18,UART_PIN_NO_CHANGE,UART_PIN_NO_CHANGE));
    ESP_ERROR_CHECK(gpio_set_direction(GPIO_NUM_4,GPIO_MODE_OUTPUT));gpio_set_level(GPIO_NUM_4,0);
    ESP_ERROR_CHECK(esp_event_handler_register(IOT_ETH_EVENT,ESP_EVENT_ANY_ID,network_event,NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT,IP_EVENT_ETH_GOT_IP,network_event,NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT,IP_EVENT_ETH_LOST_IP,network_event,NULL));
    usbh_cdc_driver_config_t cdc={.task_stack_size=4096,.task_priority=20,.task_coreid=0,
        .skip_init_usb_host_driver=false};
    ESP_ERROR_CHECK(usbh_cdc_driver_install(&cdc));
    static const usb_device_match_id_t match[]={
        {.match_flags=USB_DEVICE_ID_MATCH_VID_PID,.idVendor=0x2ecc,.idProduct=0x3012},{0}};
    iot_eth_driver_t *driver=NULL;
    if(TEST_ECM){
        iot_usbh_ecm_config_t cfg={.match_id_list=match};ESP_ERROR_CHECK(iot_eth_new_usb_ecm(&cfg,&driver));
    }else{
        iot_usbh_rndis_config_t cfg={.match_id_list=match};ESP_ERROR_CHECK(iot_eth_new_usb_rndis(&cfg,&driver));
    }
    iot_eth_handle_t eth=NULL;iot_eth_config_t eth_cfg={.driver=driver,.stack_input=NULL};
    ESP_ERROR_CHECK(iot_eth_install(&eth_cfg,&eth));
    esp_netif_inherent_config_t base=ESP_NETIF_INHERENT_DEFAULT_ETH();
    base.if_key="ML307_USB_TEST";base.if_desc="ML307 USB link probe";
    esp_netif_config_t cfg={.base=&base,.driver=NULL,.stack=ESP_NETIF_NETSTACK_DEFAULT_ETH};
    netif=esp_netif_new(&cfg);assert(netif);
    iot_eth_netif_glue_handle_t glue=iot_eth_new_netif_glue(eth);assert(glue);
    ESP_ERROR_CHECK(esp_netif_attach(netif,glue));ESP_ERROR_CHECK(iot_eth_start(eth));
    assert(xTaskCreate(at_setup,"usb_test_at",4096,NULL,5,NULL)==pdPASS);
    assert(xTaskCreate(connectivity,"usb_test_net",4096,NULL,5,NULL)==pdPASS);
}
