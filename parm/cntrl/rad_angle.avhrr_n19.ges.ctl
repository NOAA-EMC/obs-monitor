dset ^avhrr_n19.%y4%m2%d2%h2.ieee_d           
options template big_endian sequential
undef -999.
title avhrr      n19           3
*XDEF is scan position
*YDEF is channel number
*  y=    1, channel=    3 , iuse=  1 , error=    0.600 , wlth=      3.74 , freq=  80094.35
*  y=    2, channel=    4 , iuse=  1 , error=    0.680 , wlth=     10.78 , freq=  27816.45
*  y=    3, channel=    5 , iuse=  1 , error=    0.720 , wlth=     12.03 , freq=  24918.34
*ZDEF is geographic region
*  region= 1 global (180W-180E, 90S-90N)                                        
*  region= 2 land (180W-180E, 90S-90N)                                          
*  region= 3 water (180W-180E, 90S-90N)                                         
*  region= 4 ice/snow (180W-180E, 90S-90N)                                      
*  region= 5 mixed (180W-180E, 90S-90N)                                         
xdef  90 linear -52.6   1.2
ydef    3 linear 1.0 1.0
zdef  5 linear 1.0 1.0
tdef  121 linear 00Z30jan2024 06hr
vars      35
satang      1 0     satang
count       5 0      count
penalty     5 0    penalty
omgnbc      5 0     omgnbc
total       5 0      total
omgbc       5 0      omgbc
fixang      5 0     fixang
lapse       5 0      lapse
lapse2      5 0     lapse2
const       5 0      const
scangl      5 0     scangl
clw         5 0        clw
cos         5 0        cos
sin         5 0        sin
emiss       5 0      emiss
ordang4     5 0    ordang4
ordang3     5 0    ordang3
ordang2     5 0    ordang2
ordang1     5 0    ordang1
omgnbc_2    5 0   omgnbc_2
total_2     5 0    total_2
omgbc_2     5 0    omgbc_2
fixang_2    5 0   fixang_2
lapse_2     5 0    lapse_2
lapse2_2    5 0   lapse2_2
const_2     5 0    const_2
scangl_2    5 0   scangl_2
clw_2       5 0      clw_2
cos_2       5 0      cos_2
sin_2       5 0      sin_2
emiss_2     5 0    emiss_2
ordang4_2   5 0  ordang4_2
ordang3_2   5 0  ordang3_2
ordang2_2   5 0  ordang2_2
ordang1_2   5 0  ordang1_2
endvars
