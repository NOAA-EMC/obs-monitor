dset ^ompsnp_n20.anl.%y4%m2%d2%h2.ieee_d      
options template big_endian sequential
undef -999.
title ompsnp     n20          22
*XDEF is pressure level number
*  x=    1, level=      0.101 , iuse=  1 , error=    0.020
*  x=    2, level=      0.160 , iuse=  1 , error=    0.020
*  x=    3, level=      0.254 , iuse=  1 , error=    0.025
*  x=    4, level=      0.403 , iuse=  1 , error=    0.040
*  x=    5, level=      0.639 , iuse=  1 , error=    0.080
*  x=    6, level=      1.013 , iuse=  1 , error=    0.156
*  x=    7, level=      1.601 , iuse=  1 , error=    0.245
*  x=    8, level=      2.543 , iuse=  1 , error=    0.510
*  x=    9, level=      4.033 , iuse=  1 , error=    1.089
*  x=   10, level=      6.394 , iuse=  1 , error=    3.917
*  x=   11, level=     10.132 , iuse=  1 , error=    6.124
*  x=   12, level=     16.009 , iuse=  1 , error=    6.347
*  x=   13, level=     25.433 , iuse=  1 , error=    5.798
*  x=   14, level=     40.327 , iuse=  1 , error=    6.843
*  x=   15, level=     63.936 , iuse=  1 , error=    9.253
*  x=   16, level=    101.325 , iuse=  1 , error=   10.091
*  x=   17, level=    160.094 , iuse=  1 , error=   10.967
*  x=   18, level=    254.326 , iuse=  1 , error=    8.478
*  x=   19, level=    403.273 , iuse=  1 , error=    5.572
*  x=   20, level=    639.361 , iuse=  1 , error=    2.638
*  x=   21, level=   1013.250 , iuse=  1 , error=    3.525
*  x=   22, level=      0.000 , iuse= -1 , error=    7.236
*YDEF is geographic region
*  region= 1 global (180W-180E, 90S-90N)                                        
*  region= 2 70N-90N (180W-180E, 70N-90N)                                       
*  region= 3 20N-70N (180W-180E, 20N-70N)                                       
*  region= 4 20S-20N (180W-180E, 20S-20N)                                       
*  region= 5 20S-70S (180W-180E, 70S-20S)                                       
*  region= 6 70S-90S (180W-180E, 90S-70S)                                       
xdef   22 linear 1.0 1.0
ydef  6 linear 1.0 1.0
zdef 1 linear 1.0 1.0
tdef  121 linear 00Z21jan2024 06hr
vars       4
cnt        0 0        cnt
cpen       0 0       cpen
avgoma     0 0     avgoma
sdvoma     0 0     sdvoma
endvars
