#include "can_link.h"
#include "cluster_can.h"      /* generated; also checks the header compiles as C */

/* TODO: FlexCAN0 in listen-only mode (never transmit on the car bus), FlexCAN1
 * at 500 kbit/s; RX filters for the Haltech V2 ids (0x360, 0x361, 0x370,
 * 0x372, 0x3E0, 0x3E2) and the ecu-pcb ids; byte-order handling per profile;
 * private-link TX with the rolling counter and cluster_crc8(). */
static display_settings_t g_settings = { 100, false, false, 0, 0, 0.0f, 0, false, 4, 16000u, false };

void can_link_init(void) {}
void can_link_poll(uint32_t now_ms) { (void)now_ms; }
car_bus_t can_link_car(void) { car_bus_t c = {0}; return c; }
display_settings_t can_link_settings(void) { return g_settings; }
void can_link_send_motion(float kph, float rpm, float battery_v,
                          bool kph_ok, bool rpm_ok, bool batt_ok, bool from_hall)
{ (void)kph; (void)rpm; (void)battery_v; (void)kph_ok; (void)rpm_ok; (void)batt_ok; (void)from_hall; }
void can_link_send_fluids(float fuel_pct, float coolant_c, float oil_kpa,
                          bool fuel_ok, bool coolant_ok, bool oil_ok)
{ (void)fuel_pct; (void)coolant_c; (void)oil_kpa; (void)fuel_ok; (void)coolant_ok; (void)oil_ok; }
void can_link_send_indicators(bool l, bool r, bool hb, bool brake, bool alt, bool oil,
                              bool lights_on, uint8_t dimmer_pct)
{ (void)l; (void)r; (void)hb; (void)brake; (void)alt; (void)oil; (void)lights_on; (void)dimmer_pct; }
void can_link_send_power(bool ignition_on, bool suspend_request, uint8_t suspend_in_s)
{ (void)ignition_on; (void)suspend_request; (void)suspend_in_s; }
