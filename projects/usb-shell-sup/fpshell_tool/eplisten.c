/* eplisten — 對任意 VID/PID/介面/端點做 bulk IN,用來驗證推送機制。 */
#include <stdio.h>
#include <stdlib.h>
#include "libusb.h"
int main(int argc,char**argv){
    if(argc<6){fprintf(stderr,"用法: eplisten <vid> <pid> <iface> <ep> <秒>\n");return 1;}
    int vid=strtol(argv[1],0,0),pid=strtol(argv[2],0,0),ifc=atoi(argv[3]);
    int ep=strtol(argv[4],0,0),secs=atoi(argv[5]);
    libusb_context*c=0; if(libusb_init(&c))return 1;
    libusb_device_handle*h=libusb_open_device_with_vid_pid(c,vid,pid);
    if(!h){fprintf(stderr,"找不到 %04x:%04x\n",vid,pid);return 1;}
    int rc=libusb_claim_interface(h,ifc);
    printf("claim 介面 %d: %s\n",ifc,rc?libusb_error_name(rc):"OK");
    unsigned char b[4096]; int total=0;
    for(int i=0;i<secs;i++){
        int got=0;
        rc=libusb_bulk_transfer(h,ep,b,sizeof b,&got,1000);
        if(rc==0&&got>0){
            total+=got; printf("[%2ds +%d] ",i,got);
            for(int j=0;j<got&&j<64;j++)printf("%02x",b[j]);
            printf("  |");
            for(int j=0;j<got&&j<32;j++)putchar(b[j]>=32&&b[j]<127?b[j]:'.');
            printf("\n");
        } else if(rc!=LIBUSB_ERROR_TIMEOUT){printf("[%2ds] %s\n",i,libusb_error_name(rc));break;}
    }
    printf("總共 %d bytes\n",total);
    libusb_release_interface(h,ifc); libusb_close(h); libusb_exit(c); return 0;
}
