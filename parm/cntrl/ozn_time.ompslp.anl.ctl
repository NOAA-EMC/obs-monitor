dset ^ompslp_npp.anl.%y4%m2%d2%h2.ieee_d      
options template big_endian sequential
undef -999.
title ompslp     npp           1
*XDEF is pressure level number
*  x=    1, level=    999.999 , iuse=  1 , error=    9.999
*YDEF is geographic region
*  region= 1 global (180W-180E, 90S-90N)                                        
*  region= 2 70N-90N (180W-180E, 70N-90N)                                       
*  region= 3 20N-70N (180W-180E, 20N-70N)                                       
*  region= 4 20S-20N (180W-180E, 20S-20N)                                       
*  region= 5 20S-70S (180W-180E, 70S-20S)                                       
*  region= 6 70S-90S (180W-180E, 90S-70S)                                       
xdef    1 linear 1.0 1.0
ydef  6 linear 1.0 1.0
zdef 1 linear 1.0 1.0
tdef  121 linear 00Z21jan2024 06hr
vars       4
cnt        0 0        cnt
cpen       0 0       cpen
avgoma     0 0     avgoma
sdvoma     0 0     sdvoma
endvars
