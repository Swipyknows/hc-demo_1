CFLAGS = -mcpu=cortex-m3 -mthumb -g -O0 -nostdlib -ffreestanding -Wall -I.

fw.elf: main.c startup.c board.h link.ld
	arm-none-eabi-gcc $(CFLAGS) -T link.ld startup.c main.c -o fw.elf

clean:
	rm -f fw.elf
