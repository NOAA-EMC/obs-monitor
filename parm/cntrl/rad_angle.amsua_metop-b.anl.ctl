dset ^amsua_metop-b_anl.%y4%m2%d2%h2.ieee_d   
options template big_endian sequential
undef -999.
title amsua      metop-b      15
*XDEF is scan position
*YDEF is channel number
*  y=    1, channel=    1 , iuse= -1 , error=    2.500 , wlth=  12596.14 , freq=     23.80
*  y=    2, channel=    2 , iuse= -1 , error=    2.200 , wlth=   9547.08 , freq=     31.40
*  y=    3, channel=    3 , iuse= -1 , error=    2.000 , wlth=   5960.12 , freq=     50.30
*  y=    4, channel=    4 , iuse= -1 , error=    0.550 , wlth=   5677.83 , freq=     52.80
*  y=    5, channel=    5 , iuse= -1 , error=    0.300 , wlth=   5593.48 , freq=     53.60
*  y=    6, channel=    6 , iuse= -1 , error=    0.230 , wlth=   5510.92 , freq=     54.40
*  y=    7, channel=    7 , iuse= -1 , error=    0.230 , wlth=   5456.73 , freq=     54.94
*  y=    8, channel=    8 , iuse=  1 , error=    0.250 , wlth=   5401.62 , freq=     55.50
*  y=    9, channel=    9 , iuse=  1 , error=    0.250 , wlth=   5232.86 , freq=     57.29
*  y=   10, channel=   10 , iuse=  1 , error=    0.350 , wlth=   5232.86 , freq=     57.29
*  y=   11, channel=   11 , iuse=  1 , error=    0.400 , wlth=   5232.86 , freq=     57.29
*  y=   12, channel=   12 , iuse=  1 , error=    0.550 , wlth=   5232.86 , freq=     57.29
*  y=   13, channel=   13 , iuse=  1 , error=    0.800 , wlth=   5232.86 , freq=     57.29
*  y=   14, channel=   14 , iuse=  4 , error=    4.000 , wlth=   5232.86 , freq=     57.29
*  y=   15, channel=   15 , iuse= -1 , error=    3.500 , wlth=   3368.34 , freq=     89.00
*ZDEF is geographic region
*  region= 1 global (180W-180E, 90S-90N)                                        
*  region= 2 land (180W-180E, 90S-90N)                                          
*  region= 3 water (180W-180E, 90S-90N)                                         
*  region= 4 ice/snow (180W-180E, 90S-90N)                                      
*  region= 5 mixed (180W-180E, 90S-90N)                                         
xdef  30 linear -48.3   3.3
ydef   15 linear 1.0 1.0
zdef  5 linear 1.0 1.0
tdef  121 linear 00Z30jan2024 06hr
vars      35
satang      1 0     satang
count       5 0      count
penalty     5 0    penalty
omanbc      5 0     omanbc
total       5 0      total
omabc       5 0      omabc
fixang      5 0     fixang
lapse       5 0      lapse
lapse2      5 0     lapse2
const       5 0      const
scangl      5 0     scangl
clw         5 0        clw
omanbc_2    5 0   omanbc_2
sin         5 0        sin
omabc_2     5 0    omabc_2
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
