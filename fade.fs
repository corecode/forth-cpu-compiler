$100 constant GPIO
$101 constant GPIO-DIR

\ delay is 5 cycles per loop, 4.8MHz loop rate
\ we want one fade to take 1s, and run at 1kHz PWM rate
1000 constant MAX-DUTY

\ we need 4.8MHz / 1kHz / MAX-DUTY delay cycles
3 constant DELAY-LOOP

: ! !+ DROP ;

: DELAY ( n -- )
   begin
     dup
   while
     1 -
   repeat
   drop ;

variable DUTY
variable DUTY-DIR

: TOGGLE-BLINK ( n -- n ) 3 xor dup     GPIO ! ;
: INIT-IO                 3         GPIO-DIR ! ;

: DELAY-DUTY
    begin
      dup
    while
      delay-loop delay
      1 -
    repeat
    drop ;

: DUTY-MAX?        duty @ max-duty - 0= ;
: DUTY-MIN?        duty @ 0= ;
: MAYBE-SWITCH-DIR
    duty-max? duty-min? or
    if
      0 duty-dir @ -
      duty-dir !
    then ;
: NEXT-DUTY
    duty @ duty-dir @ +
    duty !
    maybe-switch-dir
;

: START init-io
        995 DUTY !
        1 DUTY-DIR !
        1                \ LED state
        begin
          toggle-blink   \ state1 -- state2
          DUTY @ delay-duty
          toggle-blink   \ state2 -- state1
          MAX-DUTY DUTY @ - delay-duty
          next-duty
        again
;
