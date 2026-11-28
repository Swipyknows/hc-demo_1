#include "board.h"

static void uart_putc(char c) { USART_DR(USART1_BASE) = c; }
static void uart_puts(const char *s) { while (*s) uart_putc(*s++); }

/* Receive-path callback, registered by the driver setup code */
void (*rx_callback)(void);
static void on_rx(void) { uart_puts("rx ok\n"); }

int main(void)
{
  USART_CR1(USART1_BASE) = USART_CR1_UE | USART_CR1_TE;
  uart_puts("boot ok\n");
  rx_callback();
  uart_puts("init done\n");
  for (;;);
}
