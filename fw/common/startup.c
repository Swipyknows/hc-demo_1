/* startup.c - reset handler and vector table shared by every benchmark case.
 * Read-only for the debugging agent. Any handler not defined in main.c falls
 * through to Default_Handler (weak alias), which spins forever. */
#include "board.h"

extern uint32_t _estack, _etext, _sdata, _edata, _sbss, _ebss;
int main(void);

void Reset_Handler(void)
{
  uint32_t *src = &_etext, *dst = &_sdata;
  while (dst < &_edata) *dst++ = *src++;
  for (dst = &_sbss; dst < &_ebss;) *dst++ = 0;
  main();
  for (;;);
}

void Default_Handler(void) { for (;;); }

void HardFault_Handler(void)
{
  const char *s = "HARDFAULT\n";
  while (*s) USART_DR(USART1_BASE) = *s++;
  for (;;);
}

#define WEAK __attribute__((weak, alias("Default_Handler")))
void NMI_Handler(void) WEAK;
void MemManage_Handler(void) WEAK;
void BusFault_Handler(void) WEAK;
void UsageFault_Handler(void) WEAK;
void SVC_Handler(void) WEAK;
void PendSV_Handler(void) WEAK;
void SysTick_Handler(void) WEAK;
void TIM2_IRQHandler(void) WEAK;

__attribute__((section(".isr_vector"), used))
void (*const vectors[16 + 29])(void) = {
  (void (*)(void))&_estack,
  Reset_Handler, NMI_Handler, HardFault_Handler, MemManage_Handler,
  BusFault_Handler, UsageFault_Handler, 0, 0, 0, 0,
  SVC_Handler, 0, 0, PendSV_Handler, SysTick_Handler,
  /* IRQ0..IRQ27 */
  Default_Handler, Default_Handler, Default_Handler, Default_Handler,
  Default_Handler, Default_Handler, Default_Handler, Default_Handler,
  Default_Handler, Default_Handler, Default_Handler, Default_Handler,
  Default_Handler, Default_Handler, Default_Handler, Default_Handler,
  Default_Handler, Default_Handler, Default_Handler, Default_Handler,
  Default_Handler, Default_Handler, Default_Handler, Default_Handler,
  Default_Handler, Default_Handler, Default_Handler, Default_Handler,
  TIM2_IRQHandler,                                   /* IRQ28 */
};
