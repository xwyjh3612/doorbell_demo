#include <assert.h>
#include <stdio.h>
#include "radar_frame_parser.h"
#include "radar_readings.h"
static radar_readings_t readings;
static bool vitals;
static void receive(void *ctx,const uint8_t *f,size_t size)
{
    (void)ctx; radar_readings_apply(&readings,f,size,1000,vitals);
}
int main(void)
{
    radar_frame_parser_t p={0};radar_readings_reset(&readings);vitals=true;
    const uint8_t breath[]={0x53,0x59,0x81,2,0,1,16,0x40,0x54,0x43};
    const uint8_t heart[]={0x53,0x59,0x85,2,0,1,76,0x80,0x54,0x43};
    const uint8_t distance[]={0x53,0x59,0x80,4,0,2,0,42,0x5c,0x54,0x43};
    radar_frame_parser_feed(&p,breath,4,receive,NULL);radar_frame_parser_feed(&p,breath+4,6,receive,NULL);
    radar_frame_parser_feed(&p,heart,sizeof(heart),receive,NULL);
    radar_frame_parser_feed(&p,distance,sizeof(distance),receive,NULL);
    assert(readings.breath==16&&readings.heart==76&&readings.distance_cm==42&&readings.heart_ms==1000);
    uint8_t bad[10];memcpy(bad,heart,10);bad[6]=255;bad[7]=0x33;
    radar_frame_parser_feed(&p,bad,10,receive,NULL);assert(readings.heart==76);
    memcpy(bad,heart,10);bad[7]^=1;radar_frame_parser_feed(&p,bad,10,receive,NULL);assert(readings.heart==76);
    const uint8_t zero[]={0x53,0x59,0x85,2,0,1,0,0x34,0x54,0x43};
    radar_frame_parser_feed(&p,zero,10,receive,NULL);assert(readings.heart==0&&readings.breath==16);
    const uint8_t empty[]={0x53,0x59,0x80,1,0,1,0,0x2e,0x54,0x43};
    radar_frame_parser_feed(&p,empty,10,receive,NULL);assert(readings.heart==-1&&readings.breath==-1);
    const uint8_t sleep[]={0x53,0x59,0x84,2,0,1,0,0x33,0x54,0x43};
    radar_frame_parser_feed(&p,sleep,10,receive,NULL);assert(readings.sleep_raw==0);
    radar_readings_reset(&readings);vitals=false;
    radar_frame_parser_feed(&p,heart,10,receive,NULL);assert(readings.heart==-1);
    radar_readings_reset(&readings);vitals=true;
    radar_frame_parser_feed(&p,breath,10,receive,NULL);
    const uint8_t init[]={0x53,0x59,5,1,0,1,15,0xc2,0x54,0x43};
    radar_frame_parser_feed(&p,init,10,receive,NULL);assert(readings.breath==-1&&readings.breath_ms==0);
    puts("R60 readings: captured values, checksum, invalid range, zero, absence, reset, raw sleep and 24G isolation passed");
}
