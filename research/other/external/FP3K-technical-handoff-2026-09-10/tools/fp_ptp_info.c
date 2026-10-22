/* Read-only PTP GetDeviceInfo probe. No session, settings, capture or reset. */
#include <libusb.h>
#include <stdint.h>
#include <stdio.h>
static uint16_t u16(const unsigned char*p){return p[0]|p[1]<<8;}
static uint32_t u32(const unsigned char*p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
int main(void){
 libusb_context*c=NULL;libusb_device_handle*h=NULL;int rc=1,n=0,claimed=0;
 unsigned char cmd[12]={12,0,0,0,1,0,1,16,0,0,0,0},buf[65536];
 if(libusb_init(&c))return 1;
 h=libusb_open_device_with_vid_pid(c,0x1003,0xc432);
 if(!h){fputs("Camera cannot be opened\n",stderr);goto done;}
 int r=libusb_claim_interface(h,0);
 if(r){fprintf(stderr,"Interface unavailable: %s (no driver detach attempted)\n",libusb_error_name(r));goto done;}
 claimed=1;
 r=libusb_bulk_transfer(h,0x01,cmd,sizeof(cmd),&n,2000);
 if(r||n!=12){fprintf(stderr,"Request failed: %s bytes=%d\n",libusb_error_name(r),n);goto done;}
 for(int i=0;i<8;i++){
  r=libusb_bulk_transfer(h,0x82,buf,sizeof(buf),&n,3000);
  if(r){fprintf(stderr,"Reply failed: %s bytes=%d\n",libusb_error_name(r),n);goto done;}
  for(int off=0;off<n;){
   if(n-off<12){fputs("Short PTP header\n",stderr);goto done;}
   uint32_t len=u32(buf+off);uint16_t type=u16(buf+off+4),code=u16(buf+off+6);
   if(len<12||len>(uint32_t)(n-off)||u32(buf+off+8)!=0){fputs("Unexpected PTP framing; stopping\n",stderr);goto done;}
   printf("container type=%u code=0x%04x bytes=%u\n",type,code,len);
   if(type==2&&code==0x1001){FILE*f=fopen("analysis/usb-ptp-device-info.bin","wb");if(!f)goto done;size_t written=fwrite(buf+off+12,1,len-12,f);fclose(f);if(written!=len-12)goto done;}
   else if(type==3){rc=code==0x2001?0:1;goto done;}
   else{fputs("Unexpected response\n",stderr);goto done;}
   off+=(int)len;
  }
 }
 done:if(claimed)libusb_release_interface(h,0);if(h)libusb_close(h);libusb_exit(c);return rc;
}
