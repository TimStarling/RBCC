#ifndef BSP_SYSTEM_H
#define BSP_SYSTEM_H

#include <stdint.h>

typedef struct
{
    uint8_t system_ready;
    uint32_t system_tick_ms;
    uint32_t scheduler_cycle_count;
	uint32_t system_mode;
	
	uint16_t light_raw;
    uint8_t light_percent;
	uint16_t temperature_raw;
	int16_t mcu_temperature_centi_c;
    uint8_t humidity_percent;
	uint16_t beep_freq;
	float dht_temp;
	float dht_hum;
	
	int16_t data_x;
	int16_t data_y;
} system_parameter;

extern system_parameter sp;

void bsp_system_init(void);

#endif
