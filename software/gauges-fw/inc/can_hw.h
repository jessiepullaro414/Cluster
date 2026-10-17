#ifndef CAN_HW_H
#define CAN_HW_H
/* The CAN controllers behind a struct of functions, so the protocol logic in can_link.c runs on the host against a fake
 * (test/test_can_link.c) and on the part against the FlexCAN driver (flexcan_s32k.c). Standard 11-bit identifiers, classic
 * frames only. One receive mailbox per accepted identifier, so a newer frame simply replaces an older unread one: the logic
 * only ever wants the latest value of each message. */
#include <stdbool.h>
#include <stdint.h>

typedef enum { CAN_BUS_CAR = 0, CAN_BUS_LINK = 1, CAN_BUS_COUNT } can_bus_t;

typedef struct {
    uint16_t id;
    uint8_t  dlc;
    uint8_t  data[8];
} can_frame_t;

#define CAN_MAX_IDS 8u

typedef struct {
    uint32_t bitrate;                   /* bit/s */
    bool     listen_only;               /* never drives the bus, not even to acknowledge a frame (the car bus) */
    uint8_t  n_rx, n_tx;
    uint16_t rx_ids[CAN_MAX_IDS];       /* identifiers to accept, one mailbox each */
    uint16_t tx_ids[CAN_MAX_IDS];       /* identifiers that will be sent, one mailbox each (empty when listen_only) */
} can_config_t;

typedef struct {
    bool (*start)(can_bus_t bus, const can_config_t *cfg);      /* (re)configure and start; false if the bit rate cannot be made */
    bool (*rx)(can_bus_t bus, can_frame_t *f);                   /* the next received frame, false if none */
    bool (*tx)(can_bus_t bus, const can_frame_t *f);             /* false if its mailbox is still busy or the bus is listen-only */
    bool (*bus_off)(can_bus_t bus);
} can_hw_t;

extern const can_hw_t can_hw_s32k;

#endif
