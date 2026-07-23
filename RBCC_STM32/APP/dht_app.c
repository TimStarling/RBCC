#include "dht_app.h"
#include "main.h"
#include "tim.h"

#define DHT_GPIO_PORT                 GPIOG
#define DHT_GPIO_PIN                  GPIO_PIN_15
#define DHT_MIN_SAMPLE_INTERVAL_MS    1000U
#define DHT_START_LOW_TIME_US        20000U
#define DHT_EDGE_TIMEOUT_US            120U
#define DHT_BIT_ONE_THRESHOLD_US        40U

typedef enum
{
    DHT_STATE_IDLE = 0,
    DHT_STATE_START_LOW,
    DHT_STATE_WAIT_RESPONSE_LOW,
    DHT_STATE_WAIT_RESPONSE_HIGH,
    DHT_STATE_WAIT_RESPONSE_END,
    DHT_STATE_WAIT_BIT_HIGH,
    DHT_STATE_WAIT_BIT_LOW
} dht_state_t;

volatile uint8_t dht_temp = 0U;
volatile uint8_t dht_hum = 0U;

static volatile dht_state_t s_dht_state = DHT_STATE_IDLE;
static volatile uint8_t s_dht_data[5];
static volatile uint8_t s_dht_bit_count;
static volatile uint32_t s_dht_high_start_us;
static uint32_t s_dht_last_start_ms;

static void dht_set_output(void)
{
    GPIO_InitTypeDef gpio_init = {0};

    gpio_init.Pin = DHT_GPIO_PIN;
    gpio_init.Mode = GPIO_MODE_OUTPUT_OD;
    gpio_init.Pull = GPIO_NOPULL;
    gpio_init.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(DHT_GPIO_PORT, &gpio_init);
}

static void dht_set_exti_input(void)
{
    GPIO_InitTypeDef gpio_init = {0};

    gpio_init.Pin = DHT_GPIO_PIN;
    gpio_init.Mode = GPIO_MODE_IT_RISING_FALLING;
    gpio_init.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(DHT_GPIO_PORT, &gpio_init);
    __HAL_GPIO_EXTI_CLEAR_IT(DHT_GPIO_PIN);
}

static void dht_schedule_timer_event(uint32_t delay_us)
{
    __HAL_TIM_DISABLE_IT(&htim2, TIM_IT_CC1);
    __HAL_TIM_CLEAR_FLAG(&htim2, TIM_FLAG_CC1);
    __HAL_TIM_SET_COMPARE(&htim2,
                          TIM_CHANNEL_1,
                          __HAL_TIM_GET_COUNTER(&htim2) + delay_us);
    __HAL_TIM_ENABLE_IT(&htim2, TIM_IT_CC1);
}

static void dht_return_to_idle(void)
{
    __HAL_TIM_DISABLE_IT(&htim2, TIM_IT_CC1);
    HAL_NVIC_DisableIRQ(EXTI15_10_IRQn);
    dht_set_output();
    HAL_GPIO_WritePin(DHT_GPIO_PORT, DHT_GPIO_PIN, GPIO_PIN_SET);
    s_dht_state = DHT_STATE_IDLE;
}

static void dht_finish_frame(void)
{
    uint8_t checksum;

    checksum = (uint8_t)(s_dht_data[0] + s_dht_data[1] +
                         s_dht_data[2] + s_dht_data[3]);

    if (checksum == s_dht_data[4])
    {
        dht_hum = s_dht_data[0];
        dht_temp = s_dht_data[2];
    }

    dht_return_to_idle();
}

static void dht_handle_edge(void)
{
    GPIO_PinState pin_level;
    uint32_t now_us;
    uint32_t high_time_us;
    uint8_t byte_index;

    pin_level = HAL_GPIO_ReadPin(DHT_GPIO_PORT, DHT_GPIO_PIN);
    now_us = __HAL_TIM_GET_COUNTER(&htim2);

    switch (s_dht_state)
    {
        case DHT_STATE_WAIT_RESPONSE_LOW:
            if (pin_level == GPIO_PIN_RESET)
            {
                s_dht_state = DHT_STATE_WAIT_RESPONSE_HIGH;
                dht_schedule_timer_event(DHT_EDGE_TIMEOUT_US);
            }
            break;

        case DHT_STATE_WAIT_RESPONSE_HIGH:
            if (pin_level == GPIO_PIN_SET)
            {
                s_dht_state = DHT_STATE_WAIT_RESPONSE_END;
                dht_schedule_timer_event(DHT_EDGE_TIMEOUT_US);
            }
            break;

        case DHT_STATE_WAIT_RESPONSE_END:
            if (pin_level == GPIO_PIN_RESET)
            {
                s_dht_state = DHT_STATE_WAIT_BIT_HIGH;
                dht_schedule_timer_event(DHT_EDGE_TIMEOUT_US);
            }
            break;

        case DHT_STATE_WAIT_BIT_HIGH:
            if (pin_level == GPIO_PIN_SET)
            {
                s_dht_high_start_us = now_us;
                s_dht_state = DHT_STATE_WAIT_BIT_LOW;
                dht_schedule_timer_event(DHT_EDGE_TIMEOUT_US);
            }
            break;

        case DHT_STATE_WAIT_BIT_LOW:
            if (pin_level == GPIO_PIN_RESET)
            {
                high_time_us = (uint32_t)(now_us - s_dht_high_start_us);
                byte_index = (uint8_t)(s_dht_bit_count >> 3U);
                s_dht_data[byte_index] <<= 1U;

                if (high_time_us > DHT_BIT_ONE_THRESHOLD_US)
                {
                    s_dht_data[byte_index] |= 1U;
                }

                s_dht_bit_count++;

                if (s_dht_bit_count >= 40U)
                {
                    dht_finish_frame();
                }
                else
                {
                    s_dht_state = DHT_STATE_WAIT_BIT_HIGH;
                    dht_schedule_timer_event(DHT_EDGE_TIMEOUT_US);
                }
            }
            break;

        default:
            break;
    }
}

static void dht_start_acquisition(void)
{
    uint8_t i;

    for (i = 0U; i < 5U; i++)
    {
        s_dht_data[i] = 0U;
    }

    s_dht_bit_count = 0U;
    HAL_NVIC_DisableIRQ(EXTI15_10_IRQn);
    dht_set_output();
    HAL_GPIO_WritePin(DHT_GPIO_PORT, DHT_GPIO_PIN, GPIO_PIN_RESET);
    s_dht_state = DHT_STATE_START_LOW;
    dht_schedule_timer_event(DHT_START_LOW_TIME_US);
}

void dht_app_init(void)
{
    if (HAL_TIM_Base_Start(&htim2) != HAL_OK)
    {
        Error_Handler();
    }

    __HAL_RCC_SYSCFG_CLK_ENABLE();
    HAL_NVIC_SetPriority(EXTI15_10_IRQn, 1U, 0U);
    HAL_NVIC_SetPriority(TIM2_IRQn, 2U, 0U);
    HAL_NVIC_EnableIRQ(TIM2_IRQn);

    dht_set_output();
    HAL_GPIO_WritePin(DHT_GPIO_PORT, DHT_GPIO_PIN, GPIO_PIN_SET);
    s_dht_last_start_ms = HAL_GetTick() - DHT_MIN_SAMPLE_INTERVAL_MS;
}

void dht_app_task(void)
{
    uint32_t now_ms;

    now_ms = HAL_GetTick();

    if ((s_dht_state == DHT_STATE_IDLE) &&
        ((uint32_t)(now_ms - s_dht_last_start_ms) >=
         DHT_MIN_SAMPLE_INTERVAL_MS))
    {
        s_dht_last_start_ms = now_ms;
        dht_start_acquisition();
    }
}

void HAL_TIM_OC_DelayElapsedCallback(TIM_HandleTypeDef *htim)
{
    if ((htim->Instance == TIM2) &&
        (htim->Channel == HAL_TIM_ACTIVE_CHANNEL_1))
    {
        if (s_dht_state == DHT_STATE_START_LOW)
        {
            HAL_GPIO_WritePin(DHT_GPIO_PORT, DHT_GPIO_PIN, GPIO_PIN_SET);
            dht_set_exti_input();
            s_dht_state = DHT_STATE_WAIT_RESPONSE_LOW;
            HAL_NVIC_EnableIRQ(EXTI15_10_IRQn);
            dht_schedule_timer_event(DHT_EDGE_TIMEOUT_US);
        }
        else if (s_dht_state != DHT_STATE_IDLE)
        {
            dht_return_to_idle();
        }
    }
}

void HAL_GPIO_EXTI_Callback(uint16_t gpio_pin)
{
    if (gpio_pin == DHT_GPIO_PIN)
    {
        dht_handle_edge();
    }
}
