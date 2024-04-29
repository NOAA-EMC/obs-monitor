dset ^ssmis_f18.%y4%m2%d2%h2.ieee_d           
options template big_endian sequential
undef -999.
title ssmis      f18          24
*XDEF is scan position
*YDEF is channel number
*  y=    1, channel=    1 , iuse= -1 , error=    1.500 , wlth=   5960.09 , freq=     50.30
*  y=    2, channel=    2 , iuse= -1 , error=    0.500 , wlth=   5677.89 , freq=     52.80
*  y=    3, channel=    3 , iuse= -1 , error=    0.500 , wlth=   5593.56 , freq=     53.60
*  y=    4, channel=    4 , iuse= -1 , error=    0.500 , wlth=   5510.89 , freq=     54.40
*  y=    5, channel=    5 , iuse= -1 , error=    0.500 , wlth=   5401.67 , freq=     55.50
*  y=    6, channel=    6 , iuse= -1 , error=    1.000 , wlth=   5232.89 , freq=     57.29
*  y=    7, channel=    7 , iuse= -1 , error=    1.000 , wlth=   5047.01 , freq=     59.40
*  y=    8, channel=    8 , iuse= -1 , error=    3.000 , wlth=   1998.62 , freq=    150.00
*  y=    9, channel=    9 , iuse= -1 , error=    3.000 , wlth=   1635.44 , freq=    183.31
*  y=   10, channel=   10 , iuse= -1 , error=    3.000 , wlth=   1635.44 , freq=    183.31
*  y=   11, channel=   11 , iuse= -1 , error=    3.000 , wlth=   1635.44 , freq=    183.31
*  y=   12, channel=   12 , iuse= -1 , error=    2.400 , wlth=  15493.15 , freq=     19.35
*  y=   13, channel=   13 , iuse= -1 , error=    1.270 , wlth=  15493.15 , freq=     19.35
*  y=   14, channel=   14 , iuse= -1 , error=    1.440 , wlth=  13482.91 , freq=     22.24
*  y=   15, channel=   15 , iuse= -1 , error=    3.000 , wlth=   8102.50 , freq=     37.00
*  y=   16, channel=   16 , iuse= -1 , error=    1.340 , wlth=   8102.50 , freq=     37.00
*  y=   17, channel=   17 , iuse= -1 , error=    1.740 , wlth=   3270.88 , freq=     91.65
*  y=   18, channel=   18 , iuse= -1 , error=    3.750 , wlth=   3270.88 , freq=     91.65
*  y=   19, channel=   19 , iuse= -1 , error=    3.000 , wlth=   4737.31 , freq=     63.28
*  y=   20, channel=   20 , iuse= -1 , error=    3.000 , wlth=   4931.39 , freq=     60.79
*  y=   21, channel=   21 , iuse= -1 , error=    2.000 , wlth=   4931.39 , freq=     60.79
*  y=   22, channel=   22 , iuse= -1 , error=    6.400 , wlth=   4931.39 , freq=     60.79
*  y=   23, channel=   23 , iuse= -1 , error=    1.000 , wlth=   4931.39 , freq=     60.79
*  y=   24, channel=   24 , iuse= -1 , error=    1.000 , wlth=   4931.39 , freq=     60.79
*ZDEF is geographic region
*  region= 1 global (180W-180E, 90S-90N)                                        
*  region= 2 land (180W-180E, 90S-90N)                                          
*  region= 3 water (180W-180E, 90S-90N)                                         
*  region= 4 ice/snow (180W-180E, 90S-90N)                                      
*  region= 5 mixed (180W-180E, 90S-90N)                                         
xdef  60 linear   0.0   1.0
ydef   24 linear 1.0 1.0
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
