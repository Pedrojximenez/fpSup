/* Optional RCD CRCT recipe. These hooks touch the driver's transient structs,
 * never stock reduction tables. A file without SEC_BINFILT passes unchanged. */
static u32 bin_config(u8 *S)
{
    u32 cur=SW(S,S_CUR);
    if (!SW(S,S_FLAG) || !SW(S,S_PICKOK) || !cur || cur>SW(S,S_NROWS)) return 0;
    u32 cfg=SW(S,S_BINFILT+4u*(cur-1u));
    return (cfg&0x800u) && (cfg&0x600u) ? cfg : 0;
}

static void ogc_binpath(u8 *S, u32 in, u32 out)
{
    u32 cfg=bin_config(S);
    if (!cfg || W(in+0x10)!=((cfg&0x200u)?3u:1u) ||
        W(in+0x14)!=((cfg&0x400u)?3u:1u)) return;
    /* Branch C already applies Hbin2: do not apply a second horizontal /3. */
    if (W(out+8)==4u && W(in+0x10)==3u && W(out+0x24)==3u) W(out+0x24)=1u;
    W(out+0x48)=(cfg>>8)&1u;
}

static void ogc_binkernel(u8 *S, u32 driver)
{
    u32 cfg=bin_config(S), k, side, middle;
    if (!cfg) return;
    if (cfg&0x200u) {
        k=cfg&7u;
        side=k==0?21u:k==1?16u:k==2?11u:k==3?8u:k==4?4u:0u;
        middle=64u-2u*side;
        B8(driver+0x29)=side; B8(driver+0x2a)=middle; B8(driver+0x2b)=side;
        for (u32 i=0;i<4;i++) {
            B8(driver+0x1cu+3*i)=side;B8(driver+0x1du+3*i)=middle;B8(driver+0x1eu+3*i)=side;
        }
    }
    if (cfg&0x400u) {
        k=(cfg>>4)&7u;
        side=k==0?1365u:k==1?1024u:k==2?683u:k==3?512u:k==4?256u:0u;
        middle=4096u-2u*side;
        for (u32 i=0;i<3;i++) {
            volatile uint16_t *v=(volatile uint16_t *)(uintptr_t)(driver+8+6*i);
            v[0]=(uint16_t)side;v[1]=(uint16_t)middle;v[2]=(uint16_t)side;
        }
    }
}
