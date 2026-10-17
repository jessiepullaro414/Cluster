#include "senders.h"

/* The sender curves of the car's own senders: NOT KNOWN YET (plan A9: they have to be measured on the real senders).
 * Until a sender has a curve of at least two points its screen shows dashes. To add one, measure the sender's resistance at
 * known levels (fuel: empty, quarter ... full, using a measured container or a known tank; coolant: in a water bath with a
 * thermometer; oil: against a pressure gauge) and list the points with ascending ohms:
 *
 *     static const sender_pt_t FUEL_CURVE[] = { { 10.0f, 100.0f }, { 73.0f, 0.0f } };      <- shape only, not data
 *     senders_set_curve(SENDER_FUEL, FUEL_CURVE, sizeof FUEL_CURVE / sizeof FUEL_CURVE[0]);
 *
 * senders_ohms() reports the live resistance of each sender for exactly this measurement. */
void sender_curves_load(void)
{
}
