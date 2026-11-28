#include "board.h"

static void uart_putc(char c) { USART_DR(USART1_BASE) = c; }
static void uart_puts(const char *s) { while (*s) uart_putc(*s++); }

/* Shadow of the output port: bit 2 = buzzer, bit 5 = status LED */
#define PIN_BUZZER 2
#define PIN_LED    5
static uint32_t port_out;

static void pin_set(uint32_t pin)   { port_out |= (1u << pin); }
static void pin_clear(uint32_t pin) { port_out &= (1u << pin); }
static uint32_t pin_read(uint32_t pin) { return (port_out >> pin) & 1u; }

int main(void)
{
  USART_CR1(USART1_BASE) = USART_CR1_UE | USART_CR1_TE;
  uart_puts("boot ok\n");

  pin_set(PIN_BUZZER);
  pin_set(PIN_LED);
  pin_clear(PIN_LED);

  uart_puts("led=");     uart_putc('0' + pin_read(PIN_LED));
  uart_puts(" buzzer="); uart_putc('0' + pin_read(PIN_BUZZER));
  uart_puts("\n");
  uart_puts("init done\n");
  for (;;);
}
