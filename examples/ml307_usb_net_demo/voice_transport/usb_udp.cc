#include "usb_udp.h"
#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>
#include <cstring>
#include <cerrno>
#include "freertos/task.h"
#include "esp_log.h"

VoiceUsbUdp::VoiceUsbUdp() { stopped_=xEventGroupCreate(); }
VoiceUsbUdp::~VoiceUsbUdp() { Disconnect(); if(stopped_)vEventGroupDelete(stopped_); }

bool VoiceUsbUdp::Connect(const std::string& host,int port)
{
    Disconnect();
    if(!stopped_)return false;
    sockaddr_in peer={};peer.sin_family=AF_INET;peer.sin_port=htons(port);
    if(inet_pton(AF_INET,host.c_str(),&peer.sin_addr)!=1){last_error_=EINVAL;return false;}
    fd_=socket(AF_INET,SOCK_DGRAM,0);
    if(fd_<0){last_error_=errno;return false;}
    timeval timeout={.tv_sec=0,.tv_usec=20000};
    if(setsockopt(fd_,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout)) ||
       connect(fd_,reinterpret_cast<sockaddr*>(&peer),sizeof(peer))){
        last_error_=errno;close(fd_);fd_=-1;return false;
    }
    connected_=true;running_=true;xEventGroupClearBits(stopped_,BIT0);
    if(xTaskCreate([](void *arg){
        auto *self=static_cast<VoiceUsbUdp*>(arg);self->receive();
        xEventGroupSetBits(self->stopped_,BIT0);vTaskDelete(nullptr);
    },"voice_usb_rx",4096,this,5,nullptr)!=pdPASS){
        connected_=false;running_=false;close(fd_);fd_=-1;return false;
    }
    return true;
}

void VoiceUsbUdp::Disconnect()
{
    if(fd_<0)return;
    bool task_running=running_.exchange(false);connected_=false;
    if(task_running){
        // recv has a 20ms timeout; do not close/reuse fd while it is receiving.
        auto bits=xEventGroupWaitBits(stopped_,BIT0,pdFALSE,pdTRUE,pdMS_TO_TICKS(1000));
        if(!(bits&BIT0)){
            ESP_LOGE("VOICE_USB_UDP","Receiver did not exit within 1s");
            // Keep waiting for safe ownership release. A teardown failure must
            // be visible and must never free a still-referenced object.
            xEventGroupWaitBits(stopped_,BIT0,pdFALSE,pdTRUE,portMAX_DELAY);
        }
    }
    close(fd_);fd_=-1;
}

int VoiceUsbUdp::Send(const std::string& data,int)
{
    if(!running_||fd_<0)return -1;
    int sent=send(fd_,data.data(),data.size(),MSG_DONTWAIT);
    if(sent<0)last_error_=errno;
    return sent; // Full queue/error drops this packet; no stale retry queue.
}

void VoiceUsbUdp::receive()
{
    std::string packet(8192,'\0');
    while(running_){
        int size=recv(fd_,packet.data(),packet.size(),0);
        if(!running_)break;
        if(size<0){
            if(errno==EAGAIN||errno==EWOULDBLOCK||errno==EINTR)continue;
            last_error_=errno;break;
        }
        if(size==0)continue;
        if(message_callback_)message_callback_(std::string(packet.data(),size));
        // The application callback publishes to the original latest mailbox,
        // replacing old unread packets. No per-packet retry/audio FIFO added.
    }
}
