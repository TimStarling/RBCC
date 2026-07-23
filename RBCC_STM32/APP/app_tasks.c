#include "app_tasks.h"
#include "bsp_system.h"
#include "uart_app.h"
#include "sensor_app.h"
#include "main.h"
#include "tim.h"
#include "ws2812_app.h"

#define APP_KEY_DEBOUNCE_MS         20U
#define APP_KEY_LONG_PRESS_MS     1000U
#define APP_KEY_REPEAT_MS          100U
#define APP_KEY_COUNT                4U
#define APP_BEEP_MIN_FREQ_HZ       2000U
#define APP_BEEP_MAX_FREQ_HZ       5000U

app_key_status_t g_app_key_status;

static uint8_t s_key_candidate;
static uint8_t s_key_long_reported;
static uint32_t s_key_candidate_since_ms;
static uint32_t s_key_press_start_ms[APP_KEY_COUNT];
static uint8_t s_beep_enabled;
static uint8_t s_beep_output_on;
static uint16_t s_beep_applied_freq;
static uint32_t s_beep_cycle_start_ms;

void beep_play(int freq)
{
    uint32_t target_freq_hz;
    uint32_t timer_clock_hz;
    uint32_t counter_clock_hz;
    uint32_t period_counts;

    if (freq < (int)APP_BEEP_MIN_FREQ_HZ)
    {
        target_freq_hz = APP_BEEP_MIN_FREQ_HZ;
    }
    else if (freq > (int)APP_BEEP_MAX_FREQ_HZ)
    {
        target_freq_hz = APP_BEEP_MAX_FREQ_HZ;
    }
    else
    {
        target_freq_hz = (uint32_t)freq;
    }

    /* APB1 timers run at twice PCLK1 when the APB1 prescaler is not 1. */
    timer_clock_hz = HAL_RCC_GetPCLK1Freq();
    if ((RCC->CFGR & RCC_CFGR_PPRE1) != 0U)
    {
        timer_clock_hz *= 2U;
    }

    counter_clock_hz = timer_clock_hz / (htim3.Init.Prescaler + 1U);
    period_counts = (counter_clock_hz + (target_freq_hz / 2U)) /
                    target_freq_hz;

    /* An even period count makes CCR1 exactly half of ARR + 1. */
    if ((period_counts & 1U) != 0U)
    {
        period_counts++;
    }

    __HAL_TIM_SET_AUTORELOAD(&htim3, period_counts - 1U);
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, period_counts / 2U);
    __HAL_TIM_SET_COUNTER(&htim3, 0U);
    htim3.Instance->EGR = TIM_EGR_UG;
}

void beep_control(int mode)
{
    if (mode == 1)
    {
        if (HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_1) != HAL_OK)
        {
            Error_Handler();
        }
    }
    else if (mode == 0)
    {
        if (HAL_TIM_PWM_Stop(&htim3, TIM_CHANNEL_1) != HAL_OK)
        {
            Error_Handler();
        }
    }
}

static void app_beep_set_output(uint8_t output_on)
{
    if (output_on != s_beep_output_on)
    {
        beep_control(output_on != 0U ? 1 : 0);
        s_beep_output_on = output_on;
    }
}

void app_beep_task(void)
{
    uint32_t elapsed_ms;
    uint32_t completed_cycles;

    if (s_beep_enabled == 0U)
    {
        app_beep_set_output(0U);
        return;
    }

    if (sp.beep_freq != s_beep_applied_freq)
    {
        beep_play(sp.beep_freq);
        s_beep_applied_freq = sp.beep_freq;
    }

    elapsed_ms = (uint32_t)(HAL_GetTick() - s_beep_cycle_start_ms);
    if (elapsed_ms >= 1500U)
    {
        completed_cycles = elapsed_ms / 1500U;
        s_beep_cycle_start_ms += completed_cycles * 1500U;
        elapsed_ms -= completed_cycles * 1500U;
    }

    app_beep_set_output(elapsed_ms < 500U ? 1U : 0U);
}

static void app_coordinate_step(uint8_t key_flags)
{
    int16_t previous_x = sp.data_x;

    if (((key_flags & APP_KEY0_MASK) != 0U) && (sp.data_x < 29))
    {
        sp.data_x++;
    }

    if (((key_flags & APP_KEY2_MASK) != 0U) && (sp.data_x > 0))
    {
        sp.data_x--;
    }

    if (sp.data_x != previous_x)
    {
        ws2812_app_show_coordinate((uint8_t)sp.data_x,
                                   0U);
    }
}

static uint8_t app_key_read_raw(void)
{
    uint8_t key_value = 0U;

    if (HAL_GPIO_ReadPin(GPIOE, GPIO_PIN_4) == GPIO_PIN_RESET)
    {
        key_value |= APP_KEY0_MASK;
    }

    if (HAL_GPIO_ReadPin(GPIOE, GPIO_PIN_3) == GPIO_PIN_RESET)
    {
        key_value |= APP_KEY1_MASK;
    }

    if (HAL_GPIO_ReadPin(GPIOE, GPIO_PIN_2) == GPIO_PIN_RESET)
    {
        key_value |= APP_KEY2_MASK;
    }

    if (HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_0) == GPIO_PIN_SET)
    {
        key_value |= APP_KEY3_MASK;
    }

    return key_value;
}

void app_tasks_init(void)
{
    uint8_t i;

    /* LED0 is active low. Keep it off until the heartbeat task runs. */
    HAL_GPIO_WritePin(GPIOF, GPIO_PIN_9, GPIO_PIN_SET);
	HAL_GPIO_WritePin(GPIOF, GPIO_PIN_8, GPIO_PIN_RESET);
	
	uart_app_init();
	sensor_app_init();
	beep_control(0);
    s_beep_enabled = 0U;
    s_beep_output_on = 0U;
    s_beep_applied_freq = sp.beep_freq;
    s_beep_cycle_start_ms = HAL_GetTick();

    g_app_key_status.current = 0U;
    g_app_key_status.down = 0U;
    g_app_key_status.up = 0U;
    g_app_key_status.long_press = 0U;
    s_key_candidate = 0U;
    s_key_long_reported = 0U;
    s_key_candidate_since_ms = HAL_GetTick();

    for (i = 0U; i < APP_KEY_COUNT; i++)
    {
        s_key_press_start_ms[i] = 0U;
    }
}

void app_key_task(void)
{
    uint8_t raw_value;
    uint8_t changed;
    uint8_t down_flags;
    uint8_t up_flags;
    uint8_t bit;
    uint8_t i;
    uint32_t now_ms;

    now_ms = HAL_GetTick();
    raw_value = app_key_read_raw();

    if (raw_value != s_key_candidate)
    {
        s_key_candidate = raw_value;
        s_key_candidate_since_ms = now_ms;
    }

    if ((s_key_candidate != g_app_key_status.current) &&
        ((uint32_t)(now_ms - s_key_candidate_since_ms) >= APP_KEY_DEBOUNCE_MS))
    {
        changed = (uint8_t)(g_app_key_status.current ^ s_key_candidate);
        down_flags = (uint8_t)(s_key_candidate & changed);
        up_flags = (uint8_t)((~s_key_candidate) & changed & APP_KEY_ALL_MASK);

        g_app_key_status.current = s_key_candidate;
        g_app_key_status.down |= down_flags;
        g_app_key_status.up |= up_flags;

        for (i = 0U; i < APP_KEY_COUNT; i++)
        {
            bit = (uint8_t)(1U << i);

            if ((down_flags & bit) != 0U)
            {
                s_key_press_start_ms[i] = now_ms;
                s_key_long_reported &= (uint8_t)(~bit);
            }

            if ((up_flags & bit) != 0U)
            {
                s_key_long_reported &= (uint8_t)(~bit);
            }
        }
    }

    for (i = 0U; i < APP_KEY_COUNT; i++)
    {
        bit = (uint8_t)(1U << i);

        if (((g_app_key_status.current & bit) != 0U) &&
            ((s_key_long_reported & bit) == 0U) &&
            ((uint32_t)(now_ms - s_key_press_start_ms[i]) >= APP_KEY_LONG_PRESS_MS))
        {
            g_app_key_status.long_press |= bit;
            s_key_long_reported |= bit;
        }
    }
}

uint8_t app_key_get_current(void)
{
    return g_app_key_status.current;
}

uint8_t app_key_get_down(void)
{
    return g_app_key_status.down;
}

uint8_t app_key_get_up(void)
{
    return g_app_key_status.up;
}

uint8_t app_key_get_long_press(void)
{
    return g_app_key_status.long_press;
}

uint8_t app_key_take_down(uint8_t key_mask)
{
    uint8_t flags = (uint8_t)(g_app_key_status.down & key_mask);
    g_app_key_status.down &= (uint8_t)(~flags);
    return flags;
}

uint8_t app_key_take_up(uint8_t key_mask)
{
    uint8_t flags = (uint8_t)(g_app_key_status.up & key_mask);
    g_app_key_status.up &= (uint8_t)(~flags);
    return flags;
}

uint8_t app_key_take_long_press(uint8_t key_mask)
{
    uint8_t flags = (uint8_t)(g_app_key_status.long_press & key_mask);
    g_app_key_status.long_press &= (uint8_t)(~flags);
    return flags;
}

void app_control_task(void)
{
    static uint8_t coordinate_repeat_flags;
    static uint32_t coordinate_repeat_ms;
    uint8_t down_flags;
    uint8_t long_press_flags;
    uint32_t now_ms;

    now_ms = HAL_GetTick();
    down_flags = app_key_take_down(APP_KEY_ALL_MASK);
    if ((down_flags & APP_KEY3_MASK) != 0U)
    {
        s_beep_enabled ^= 1U;
        s_beep_cycle_start_ms = now_ms;

        if (s_beep_enabled != 0U)
        {
            beep_play(sp.beep_freq);
            s_beep_applied_freq = sp.beep_freq;
            app_beep_set_output(1U);
        }
        else
        {
            app_beep_set_output(0U);
        }

        down_flags &= (uint8_t)(~APP_KEY3_MASK);
    }

    if (down_flags != 0U)
    {
        app_coordinate_step(down_flags);
    }

    long_press_flags = app_key_take_long_press(APP_KEY_ALL_MASK);
    if (long_press_flags != 0U)
    {
        coordinate_repeat_flags |= long_press_flags;
        coordinate_repeat_ms = now_ms;
        app_coordinate_step(long_press_flags);
    }

    coordinate_repeat_flags &= app_key_get_current();

    if ((coordinate_repeat_flags != 0U) &&
        ((uint32_t)(now_ms - coordinate_repeat_ms) >= APP_KEY_REPEAT_MS))
    {
        coordinate_repeat_ms = now_ms;
        app_coordinate_step(coordinate_repeat_flags);
    }
}

void app_light_sensor_task(void)
{
    light_sensor_task();
}

void app_temperature_sensor_task(void)
{
    temperature_sensor_task();
}

void app_uart_task(void)
{
    uart_app_task();
}

void app_heartbeat_task(void)
{
	HAL_GPIO_TogglePin(GPIOF,GPIO_PIN_9);
}
