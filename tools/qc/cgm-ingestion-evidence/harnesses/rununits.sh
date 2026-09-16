#!/bin/bash
SP=/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/c0ce5365-48f5-4392-a1ae-c72d32aabe91/scratchpad
W=/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work
run(){ cd $W/$1 && timeout 900 npm run test:unit > $SP/unit-$1.log 2>&1; echo "$1 exit=$?" >> $SP/units-summary.txt; }
run crm-bf-cache &
run crm-bf-auth &
run crm-bf-reads &
wait
run crm-bf-coercion &
run crm-bf-food &
run crm-bf-merge &
wait
run crm-bf-parms &
wait
echo DONE >> $SP/units-summary.txt
