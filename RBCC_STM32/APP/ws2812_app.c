#include "ws2812_app.h"

#include <string.h>

#include "main.h"

/* WS2812B, 800 kHz, GRB byte order. */
#define WS2812_T0H_NS       350UL
#define WS2812_T1H_NS       700UL
#define WS2812_BIT_NS      1250UL
#define WS2812_NS_PER_SEC 1000000000UL

typedef struct
{
    uint8_t green;
    uint8_t red;
    uint8_t blue;
} ws2812_pixel_t;

static ws2812_pixel_t s_pixels[WS2812_LED_COUNT];
static uint32_t s_t0h_cycles;
static uint32_t s_t1h_cycles;
static uint32_t s_bit_cycles;
static GPIO_TypeDef *s_active_port;
static uint16_t s_active_pin;

static uint32_t ws2812_ns_to_cycles(uint32_t nanoseconds)
{
    return (uint32_t)((((uint64_t)SystemCoreClock * nanoseconds) +
                       (WS2812_NS_PER_SEC - 1UL)) /
                      WS2812_NS_PER_SEC);
}

static __inline void ws2812_wait_cycles(uint32_t start, uint32_t cycles)
{
    while ((uint32_t)(DWT->CYCCNT - start) < cycles)
    {
    }
}

static __inline void ws2812_write_bit(uint8_t bit_value)
{
    uint32_t start;
    uint32_t high_cycles;

    high_cycles = (bit_value != 0U) ? s_t1h_cycles : s_t0h_cycles;
    s_active_port->BSRR = s_active_pin;
    start = DWT->CYCCNT;
    ws2812_wait_cycles(start, high_cycles);
    s_active_port->BSRR = (uint32_t)s_active_pin << 16U;
    ws2812_wait_cycles(start, s_bit_cycles);
}

static void ws2812_write_byte(uint8_t value)
{
    uint8_t mask;

    for (mask = 0x80U; mask != 0U; mask >>= 1U)
    {
        ws2812_write_bit((uint8_t)(value & mask));
    }
}

static void ws2812_set_pixel(uint16_t index,
                             uint8_t red,
                             uint8_t green,
                             uint8_t blue)
{
    if (index >= WS2812_LED_COUNT)
    {
        return;
    }

    s_pixels[index].green = green;
    s_pixels[index].red = red;
    s_pixels[index].blue = blue;
}

static void ws2812_show_on(GPIO_TypeDef *gpio_port, uint16_t gpio_pin)
{
    uint16_t index;
    uint32_t primask;

    /* Keep interrupts out of the approximately 300 us waveform. */
    primask = __get_PRIMASK();
    __disable_irq();
    s_active_port = gpio_port;
    s_active_pin = gpio_pin;

    for (index = 0U; index < WS2812_LED_COUNT; index++)
    {
        ws2812_write_byte(s_pixels[index].green);
        ws2812_write_byte(s_pixels[index].red);
        ws2812_write_byte(s_pixels[index].blue);
    }

    s_active_port->BSRR = (uint32_t)s_active_pin << 16U;
    __set_PRIMASK(primask);

    /* WS2812 reset/latch time is at least 50 us. */
    HAL_Delay(1U);
}

void ws2812_app_show_coordinate(uint8_t x, uint8_t y)
{
    uint16_t index;
    uint16_t center_index;

    /*
     * PC7 and PC8 are bound. All pixels are green by default, the red
     * center follows x, and positions x+-1 and x+-2 are yellow.
     */
    (void)y;
    for (index = 0U; index < WS2812_LED_COUNT; index++)
    {
        ws2812_set_pixel(index, 0U, 80U, 0U);
    }

    if (x < WS2812_LED_COUNT)
    {
        center_index = (uint16_t)(WS2812_LED_COUNT - 1U - x);

        if (center_index >= 2U)
        {
            ws2812_set_pixel(center_index - 2U, 80U, 80U, 0U);
        }
        if (center_index >= 1U)
        {
            ws2812_set_pixel(center_index - 1U, 80U, 80U, 0U);
        }
        ws2812_set_pixel(center_index, 80U, 0U, 0U);
        if (center_index + 1U < WS2812_LED_COUNT)
        {
            ws2812_set_pixel(center_index + 1U, 80U, 80U, 0U);
        }
        if (center_index + 2U < WS2812_LED_COUNT)
        {
            ws2812_set_pixel(center_index + 2U, 80U, 80U, 0U);
        }
    }
    ws2812_show_on(WS2812_DATA_GPIO_Port, WS2812_DATA_Pin);
    ws2812_show_on(WS2812_DATA2_GPIO_Port, WS2812_DATA2_Pin);
}

void ws2812_app_init(void)
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0U;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;

    s_t0h_cycles = ws2812_ns_to_cycles(WS2812_T0H_NS);
    s_t1h_cycles = ws2812_ns_to_cycles(WS2812_T1H_NS);
    s_bit_cycles = ws2812_ns_to_cycles(WS2812_BIT_NS);

    memset(s_pixels, 0, sizeof(s_pixels));
    WS2812_DATA_GPIO_Port->BSRR = (uint32_t)WS2812_DATA_Pin << 16U;
    WS2812_DATA2_GPIO_Port->BSRR = (uint32_t)WS2812_DATA2_Pin << 16U;
    HAL_Delay(1U);

    /* Start with both strips off; the scheduler applies the current coordinate. */
    ws2812_app_show_coordinate(0xFFU, 0xFFU);
}
