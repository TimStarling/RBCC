#ifndef WS2812_APP_H
#define WS2812_APP_H

#include <stdint.h>

#define WS2812_LED_COUNT 30U

void ws2812_app_init(void);
void ws2812_app_show_coordinate(uint8_t x, uint8_t y);

#endif
