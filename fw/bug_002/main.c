#include "board.h"

static void uart_putc(char c) { USART_DR(USART1_BASE) = c; }
static void uart_puts(const char *s) { while (*s) uart_putc(*s++); }

/* Event log kept in the last 256 bytes of SRAM so it survives a warm reset */
#define LOG_ENTRIES 64
#define LOG_BASE    (SRAM_BASE + SRAM_SIZE - LOG_ENTRIES * 4)
static uint32_t *const event_log = (uint32_t *)LOG_BASE;

static void log_event(uint32_t offset, uint32_t value)
{
  event_log[offset] = value;
}

int main(void)
{
  USART_CR1(USART1_BASE) = USART_CR1_UE | USART_CR1_TE;
  uart_puts("boot ok\n");

  for (uint32_t i = 0; i < LOG_ENTRIES; i++)
    log_event(i * sizeof(uint32_t), 0xA5000000u | i);

  uint32_t sum = 0;
  for (uint32_t i = 0; i < LOG_ENTRIES; i++)
    sum += event_log[i] & 0xFF;
  uart_puts(sum == 2016 ? "log ok\n" : "log corrupt\n");
  uart_puts("init done\n");
  for (;;);
}
