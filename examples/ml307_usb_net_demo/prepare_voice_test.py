"""Generate an isolated USB-media voice experiment from the committed baseline.

No baseline source edits, serial/flash operations, protocol or server changes.
Existing AT MQTT is retained to isolate the change in UDP media transport.
"""
from pathlib import Path
import hashlib,json,subprocess,shutil,zipfile
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
TARGET=ROOT/'build/voice-usb-evaluation-recovery'
baseline='b932fba5a14013653ef8f2e9756969b756e59a54'
subprocess.run(['git','cat-file','-e',baseline+'^{commit}'],cwd=ROOT,check=True)
TARGET.mkdir(parents=True,exist_ok=True)
record=TARGET/'baseline.json'
if not record.exists():
    archive=ROOT/'build/voice-usb-recovery-baseline.zip'
    subprocess.run(['git','archive','--format=zip',f'--output={archive}',baseline],cwd=ROOT,check=True)
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            if not (TARGET/item.filename).resolve().is_relative_to(TARGET.resolve()):raise RuntimeError('Unsafe archive path')
        z.extractall(TARGET)
    record.write_text(json.dumps({'baseline_commit':baseline,'root':str(ROOT)},indent=2),encoding='utf-8')
else:
    prior=json.loads(record.read_text())
    if prior['baseline_commit']!=baseline:raise RuntimeError('HEAD changed; preserve existing experiment and use a new isolated directory')
def original(path):
    return subprocess.check_output(['git','show',f'{baseline}:{path}'],cwd=ROOT).decode('utf-8')
def substitute(text,old,new):
    if text.count(old)!=1:raise RuntimeError('Unexpected source anchor: '+old[:80])
    return text.replace(old,new)

main=TARGET/'main'
for name in ['usb_link.cpp','usb_udp.h','usb_udp.cc']:shutil.copyfile(HERE/'voice_transport'/name,main/name)
cm=original('main/CMakeLists.txt')
cm=cm.replace('"ml307_udp_socket.cc"','"ml307_udp_socket.cc" "usb_link.cpp" "usb_udp.cc"')
# Retain main component's implicit dependency set. Explicit REQUIRES here would
# drop the baseline's implicit audio/codec/JSON dependencies.
(main/'CMakeLists.txt').write_text(cm,encoding='utf-8')
manifest=main/'idf_component.yml'
if manifest.exists():
    import yaml
    doc=yaml.safe_load(manifest.read_text(encoding='utf-8')) or {}
else:doc={'dependencies':{}}
doc.setdefault('dependencies',{})
for name in ['rndis','ecm']:
    doc['dependencies']['espressif/iot_usbh_'+name]={'version':'0.5.3' if name=='rndis' else '0.4.0',
        'override_path':str(ROOT/f'build/esp-iot-solution-cellular/components/usb/iot_usbh_{name}').replace('\\','/')}
import yaml
manifest.write_text(yaml.safe_dump(doc,sort_keys=False),encoding='utf-8')
# Regenerate from baseline on repeat to avoid duplicate config blocks.
cfg=original('main/Kconfig.projbuild')
cfg+='\nconfig VOICE_TEST_ECM\n    bool "USB ECM experiment (default RNDIS)"\n    default n\n'
(main/'Kconfig.projbuild').write_text(cfg,encoding='utf-8')

network=original('main/network_4g.cpp')
network='extern "C" bool voice_usb_start();\n'+network
network=substitute(network,'// 打印模组信息','if (!voice_usb_start()) { ESP_LOGE(TAG, "USB transport unavailable; test startup aborted"); return; }\n\n        // 打印模组信息')
(main/'network_4g.cpp').write_text(network,encoding='utf-8')
udp=original('main/ml307_udp_socket.cc')
udp='#include "usb_udp.h"\nextern "C" bool voice_usb_local_address(unsigned char *bytes);\n'+udp
udp=substitute(udp,'conn->udp = modem->CreateUdp(id);','(void)id; conn->udp = std::make_unique<VoiceUsbUdp>();')
start=udp.index('    AtModem *m = Network4g::GetModemInstance();',udp.index('int udp_get_local_address('))
end=udp.index('    return 0;',start)
udp=udp[:start]+'    if (!voice_usb_local_address(addr->ipv4)) return -1;\n'+udp[end:]
start=udp.index('int ports_resolve_addr(');end=udp.index('\nint ports_get_host_addr(',start)
udp=udp[:start]+'''int ports_resolve_addr(const char *host, esp_peer_addr_t *addr) {
    addrinfo hints={},*found=nullptr;hints.ai_family=AF_INET;hints.ai_socktype=SOCK_DGRAM;
    if(getaddrinfo(host,nullptr,&hints,&found)||!found)return -1;
    auto *v4=reinterpret_cast<sockaddr_in*>(found->ai_addr);
    addr->family=AF_INET;addr->port=0;memcpy(addr->ipv4,&v4->sin_addr,4);freeaddrinfo(found);return 0;
}
''' +udp[end:]
(main/'ml307_udp_socket.cc').write_text(udp,encoding='utf-8')

seed=ROOT/'build/firmware-profile/sdkconfig'
if not seed.exists():seed=ROOT/'sdkconfig'
lines=seed.read_text(encoding='utf-8').splitlines()
prefixes=['CONFIG_ESP_CONSOLE_USB','CONFIG_ESP_CONSOLE_SECONDARY_USB','CONFIG_USB_HOST_CONTROL_TRANSFER_MAX_SIZE=',
          'CONFIG_USBH_CDC_CONTROL_TRANSFER_BUFFER_SIZE=','CONFIG_LWIP_UDP_RECVMBOX_SIZE=','CONFIG_LWIP_TCPIP_RECVMBOX_SIZE=',
          'CONFIG_VOICE_TEST_ECM=']
lines=[line for line in lines if not any(line.startswith(p) for p in prefixes)]
lines+=['CONFIG_ESP_CONSOLE_UART_DEFAULT=y','CONFIG_ESP_CONSOLE_SECONDARY_NONE=y',
        'CONFIG_USB_HOST_CONTROL_TRANSFER_MAX_SIZE=512','CONFIG_USBH_CDC_CONTROL_TRANSFER_BUFFER_SIZE=1025',
        'CONFIG_LWIP_UDP_RECVMBOX_SIZE=8','CONFIG_LWIP_TCPIP_RECVMBOX_SIZE=16',
        '# CONFIG_VOICE_TEST_ECM is not set']
(TARGET/'usb-rndis-defaults').write_text('\n'.join(lines)+'\n',encoding='utf-8')
evidence={'baseline_commit':baseline,'official_peer_changed':False,'mqtt_protocol_changed':False,
          'mqtt_lifetime_recovery_fix_included':True,
          'app_wss_changed':False,'latest_packet_mailbox_retained':True,'at_mqtt_retained':True,
          'media_send_nonblocking':True,'built':False,'flashed':False,'voice_tested':False,
          'change_scope':'Independent copied experiment: native USB UDP media; existing MQTT AT/signaling/audio retained.',
          'limitations':['USB mode must be preconfigured; no automatic reset','USB network recovery policy requires real hardware testing',
                         'No actual voice-call evidence until USB wiring and flashing are performed'],
          'changed_files':['main/CMakeLists.txt','main/idf_component.yml','main/Kconfig.projbuild','main/network_4g.cpp',
                           'main/ml307_udp_socket.cc','main/usb_link.cpp','main/usb_udp.h','main/usb_udp.cc']}
(TARGET/'experiment.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
print('Prepared isolated voice USB-media experiment:',TARGET)
