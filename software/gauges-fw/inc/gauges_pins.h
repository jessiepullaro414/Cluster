#ifndef GAUGES_PINS_H
#define GAUGES_PINS_H
/*
 * Pin claims for gauges/ rev C. Numbers are the 64-LQFP package pins; port
 * names are from NXP's S32K1xx IO table as recorded in
 * ../../gauges/build_schematic.py (single source of truth, regenerate this
 * file from it if the schematic changes).
 */

/* car bus, FlexCAN0 */
#define PIN_CAN0_RX        6   /* PTE4 */
#define PIN_CAN0_TX        5   /* PTE5 */
#define PIN_CAN0_EN        18  /* PTB5, TJA1043T EN */
#define PIN_CAN0_STB_N     19  /* PTB4, TJA1043T STB_N */
/* private link to display/, FlexCAN1 */
#define PIN_CAN1_RX        52  /* PTC6 */
#define PIN_CAN1_TX        51  /* PTC7 */
#define PIN_CAN1_STB       60  /* PTE0, TCAN1044V standby */

/* timer capture (FTM1) */
#define PIN_SPEED_IN       58  /* PTA10, FTM1_CH4, Hall speed pulses */
#define PIN_TACH_IN        57  /* PTA11, FTM1_CH5, tach pulses */

/* ignition: pin interrupt, wakes the part from STOP/VLPS */
#define PIN_IGN_SENSE      59  /* PTE1 */

/* resistive senders and battery (ADC) */
#define PIN_ADC_FUEL       50  /* PTA0, ADC0_SE0 */
#define PIN_ADC_OIL        49  /* PTA1, ADC0_SE1 */
#define PIN_ADC_TEMP       48  /* PTA2, ADC1_SE0 */
#define PIN_ADC_BATT       47  /* PTA3, ADC1_SE1 */
#define PIN_DIM_ADC        31  /* PTB3, ADC0_SE7, dash dimmer feed */

/* six 12 V-active indicator lamps (active-low if the DNP pull-up is fitted) */
#define PIN_LAMP_TURN_L    35  /* PTC9 */
#define PIN_LAMP_TURN_R    36  /* PTC8 */
#define PIN_LAMP_HIGH_BEAM 37  /* PTA7 */
#define PIN_LAMP_BRAKE     38  /* PTA6 */
#define PIN_LAMP_ALT       43  /* PTB12 */
#define PIN_LAMP_OIL       44  /* PTD4 */

/* four GC9A01 aux gauges on LPSPI2 */
#define PIN_LPSPI2_SCK     29  /* PTC15 */
#define PIN_LPSPI2_SIN     26  /* PTC0 */
#define PIN_LPSPI2_SOUT    25  /* PTC1 */
#define PIN_LPSPI2_PCS0    30  /* PTC14 (claimed, unused: chip selects are GPIO) */
#define PIN_AUX_CS0        13  /* PTE3 */
#define PIN_AUX_CS1        14  /* PTD16 */
#define PIN_AUX_CS2        15  /* PTD15 */
#define PIN_AUX_CS3        16  /* PTE9 */
#define PIN_AUX_DC0        17  /* PTE8 */
#define PIN_AUX_DC1        22  /* PTD7 */
#define PIN_AUX_DC2        23  /* PTD6 */
#define PIN_AUX_DC3        24  /* PTD5 */
#define PIN_AUX_RST        42  /* PTB13 */
#define PIN_BL_EN          39  /* PTE7, aux backlight switch */

/* debug */
#define PIN_SWDIO          64  /* PTA4 */
#define PIN_SWCLK          62  /* PTC4 */

#endif
