* ============================================================================
* XA analog implementation of the VCS cell named ftc_sensor_ams.
* The port order mirrors ftc_sensor_ams_stub.sv exactly after bus expansion.
* This wrapper is the only analog implementation selected by use_spice.
* ============================================================================
.SUBCKT ftc_sensor_ams Q_FINAL S_SCLK S_RESET \
+ medium_therm[15] medium_therm[14] medium_therm[13] medium_therm[12] \
+ medium_therm[11] medium_therm[10] medium_therm[9] medium_therm[8] \
+ medium_therm[7] medium_therm[6] medium_therm[5] medium_therm[4] \
+ medium_therm[3] medium_therm[2] medium_therm[1] medium_therm[0] \
+ fine_therm[9] fine_therm[8] fine_therm[7] fine_therm[6] fine_therm[5] \
+ fine_therm[4] fine_therm[3] fine_therm[2] fine_therm[1] fine_therm[0] \
+ VDD VSS
XFTC_SENSOR Q_FINAL S_SCLK S_RESET \
+ medium_therm[15] medium_therm[14] medium_therm[13] medium_therm[12] \
+ medium_therm[11] medium_therm[10] medium_therm[9] medium_therm[8] \
+ medium_therm[7] medium_therm[6] medium_therm[5] medium_therm[4] \
+ medium_therm[3] medium_therm[2] medium_therm[1] medium_therm[0] \
+ fine_therm[9] fine_therm[8] fine_therm[7] fine_therm[6] fine_therm[5] \
+ fine_therm[4] fine_therm[3] fine_therm[2] fine_therm[1] fine_therm[0] \
+ VDD VSS FTC_SENSOR
.ENDS ftc_sensor_ams
