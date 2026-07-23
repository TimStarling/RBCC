#include "uart_app.h"
#include "bsp_system.h"
#include "dht_app.h"
#include "usart.h"
#include "ws2812_app.h"

#include <stdio.h>
#include <string.h>

#define UART_RX_BUFFER_SIZE 256U
#define UART_BEEP_PREFIX_LENGTH 5U
#define UART_BEEP_DIGIT_COUNT   4U
#define UART_BEEP_MIN_FREQ_HZ   2000U
#define UART_BEEP_MAX_FREQ_HZ   5000U
#define UART_LOCAL_PREFIX_LENGTH 7U
#define UART_LOCAL_MAX_COORD     29U

static uint8_t s_uart_rx_byte;
static uint8_t s_uart_rx_buffer[UART_RX_BUFFER_SIZE];
static volatile uint16_t s_uart_rx_head;
static volatile uint16_t s_uart_rx_tail;
static uint8_t s_beep_prefix_index;
static uint8_t s_beep_digit_count;
static uint16_t s_beep_command_value;
static uint8_t s_local_prefix_index;
static uint8_t s_local_parse_state;
static uint8_t s_local_digit_count;
static uint16_t s_local_x;
static uint16_t s_local_y;

static void uart_local_parser_reset(uint8_t data)
{
    s_local_prefix_index = (data == 'l') ? 1U : 0U;
    s_local_parse_state = 0U;
    s_local_digit_count = 0U;
    s_local_x = 0U;
    s_local_y = 0U;
}

static void uart_process_local_command(uint8_t data)
{
    static const uint8_t local_prefix[UART_LOCAL_PREFIX_LENGTH] =
        {'l', 'o', 'c', 'a', 'l', ':', '('};

    if (s_local_parse_state == 0U)
    {
        if (data == local_prefix[s_local_prefix_index])
        {
            s_local_prefix_index++;
            if (s_local_prefix_index == UART_LOCAL_PREFIX_LENGTH)
            {
                s_local_parse_state = 1U;
                s_local_digit_count = 0U;
                s_local_x = 0U;
            }
        }
        else
        {
            uart_local_parser_reset(data);
        }
        return;
    }

    if (s_local_parse_state == 1U)
    {
        if ((data >= '0') && (data <= '9'))
        {
            s_local_x = (uint16_t)((s_local_x * 10U) + (data - '0'));
            s_local_digit_count++;
            if (s_local_x > UART_LOCAL_MAX_COORD)
            {
                uart_local_parser_reset(data);
            }
        }
        else if ((data == ',') && (s_local_digit_count != 0U))
        {
            s_local_parse_state = 2U;
            s_local_digit_count = 0U;
            s_local_y = 0U;
        }
        else
        {
            uart_local_parser_reset(data);
        }
        return;
    }

    if ((data >= '0') && (data <= '9'))
    {
        s_local_y = (uint16_t)((s_local_y * 10U) + (data - '0'));
        s_local_digit_count++;
        if (s_local_y > UART_LOCAL_MAX_COORD)
        {
            uart_local_parser_reset(data);
        }
    }
    else if ((data == ')') && (s_local_digit_count != 0U))
    {
        sp.data_x = (int16_t)s_local_x;
        sp.data_y = (int16_t)s_local_y;
        ws2812_app_show_coordinate((uint8_t)sp.data_x, 0U);
        uart_local_parser_reset(data);
    }
    else
    {
        uart_local_parser_reset(data);
    }
}

static void uart_process_beep_command(uint8_t data)
{
    static const uint8_t beep_prefix[UART_BEEP_PREFIX_LENGTH] =
        {'b', 'e', 'e', 'p', ':'};

    if (s_beep_prefix_index < UART_BEEP_PREFIX_LENGTH)
    {
        if (data == beep_prefix[s_beep_prefix_index])
        {
            s_beep_prefix_index++;

            if (s_beep_prefix_index == UART_BEEP_PREFIX_LENGTH)
            {
                s_beep_digit_count = 0U;
                s_beep_command_value = 0U;
            }
        }
        else
        {
            s_beep_prefix_index = (data == 'b') ? 1U : 0U;
        }

        return;
    }

    if ((data >= '0') && (data <= '9'))
    {
        s_beep_command_value =
            (uint16_t)((s_beep_command_value * 10U) + (data - '0'));
        s_beep_digit_count++;

        if (s_beep_digit_count >= UART_BEEP_DIGIT_COUNT)
        {
            if (s_beep_command_value < UART_BEEP_MIN_FREQ_HZ)
            {
                sp.beep_freq = UART_BEEP_MIN_FREQ_HZ;
            }
            else if (s_beep_command_value > UART_BEEP_MAX_FREQ_HZ)
            {
                sp.beep_freq = UART_BEEP_MAX_FREQ_HZ;
            }
            else
            {
                sp.beep_freq = s_beep_command_value;
            }

            s_beep_prefix_index = 0U;
            s_beep_digit_count = 0U;
        }
    }
    else
    {
        s_beep_prefix_index = (data == 'b') ? 1U : 0U;
        s_beep_digit_count = 0U;
    }
}

static uint8_t uart_rx_pop(uint8_t *data)
{
    uint16_t tail;

    tail = s_uart_rx_tail;
    if (tail == s_uart_rx_head)
    {
        return 0U;
    }

    *data = s_uart_rx_buffer[tail];
    s_uart_rx_tail = (uint16_t)((tail + 1U) % UART_RX_BUFFER_SIZE);
    return 1U;
}

void uart_app_init(void)
{
    static const uint8_t start_message[] =
        "\r\nRBCC scheduler started\r\n";

    s_uart_rx_head = 0U;
    s_uart_rx_tail = 0U;
    s_beep_prefix_index = 0U;
    s_beep_digit_count = 0U;
    s_beep_command_value = 0U;
    s_local_prefix_index = 0U;
    s_local_parse_state = 0U;
    s_local_digit_count = 0U;
    s_local_x = 0U;
    s_local_y = 0U;

    HAL_UART_Transmit(&huart1,
                      (uint8_t *)start_message,
                      sizeof(start_message) - 1U,
                      100U);

    HAL_UART_Receive_IT(&huart1, &s_uart_rx_byte, 1U);
}

void uart_app_task(void)
{
    static uint32_t last_report_ms;
    static uint8_t echo_buffer[UART_RX_BUFFER_SIZE];
    uint32_t now_ms;
    uint8_t data;
    uint16_t echo_length;
    char buffer[128];
	now_ms = HAL_GetTick();
    echo_length = 0U;


    /* 处理串口接收到的单个字符 */
    while (uart_rx_pop(&data) != 0U)
    {
        echo_buffer[echo_length] = data;
        echo_length++;

        uart_process_beep_command(data);
        uart_process_local_command(data);

        if (data == 0x01U)
        {
            HAL_GPIO_WritePin(GPIOF, GPIO_PIN_9, GPIO_PIN_SET);
            sp.system_mode = 1U;
        }
        else if (data == 0x02U)
        {
            HAL_GPIO_WritePin(GPIOF, GPIO_PIN_9, GPIO_PIN_RESET);
            sp.system_mode = 0U;
        }
        else if (data == 0x03U)
        {
            HAL_GPIO_WritePin(GPIOF, GPIO_PIN_8, GPIO_PIN_SET);
        }
        else if (data == 0x04U)
        {
            HAL_GPIO_WritePin(GPIOF, GPIO_PIN_8, GPIO_PIN_RESET);
        }
    }

    /* 每秒发送一次调度器状态 */
    if (echo_length != 0U)
    {
        HAL_UART_Transmit(&huart1,
                          echo_buffer,
                          echo_length,
                          100U);
    }

    if ((uint32_t)(now_ms - last_report_ms) >= 1000U)
    {
        last_report_ms = now_ms;

        snprintf(buffer,
         sizeof(buffer),
         "\r\ntick=%lu mode=%lu "
         "light=%u%% raw=%u "
         "temp=%uC raw=%u "
         "humidity=%u%% "
         "(%d,%d)\r\n",
         (unsigned long)sp.system_tick_ms,
         (unsigned long)sp.system_mode,
         sp.light_percent,
         sp.light_raw,
         (unsigned int)dht_temp,
         (sp.temperature_raw),
         (unsigned int)dht_hum,
         sp.data_x,
         sp.data_y);

        HAL_UART_Transmit(&huart1,
                          (uint8_t *)buffer,
                          strlen(buffer),
                          100U);
    }
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART1)
    {
        uint16_t next_head;

        next_head = (uint16_t)((s_uart_rx_head + 1U) % UART_RX_BUFFER_SIZE);
        if (next_head != s_uart_rx_tail)
        {
            s_uart_rx_buffer[s_uart_rx_head] = s_uart_rx_byte;
            s_uart_rx_head = next_head;
        }

        HAL_UART_Receive_IT(&huart1, &s_uart_rx_byte, 1U);
    }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART1)
    {
        HAL_UART_Receive_IT(&huart1, &s_uart_rx_byte, 1U);
    }
}
