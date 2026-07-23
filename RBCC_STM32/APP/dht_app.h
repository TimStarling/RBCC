#ifndef DHT_APP_H
#define DHT_APP_H

#include <stdint.h>

extern volatile uint8_t dht_temp;
extern volatile uint8_t dht_hum;

void dht_app_init(void);
void dht_app_task(void);

#endif
