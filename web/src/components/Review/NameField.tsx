import { useId, useRef, useState } from 'react';
import { OptionList, useFieldPlace } from '@/components/Review/OptionList';
import { matching } from '@/components/Review/helpers/players';

/** A name's field: what is typed stays as typed. A list under it proposes the `names` it matches,
 * whatever the accents: only a click, or the arrows then Enter, picks one. */
export function NameField({
  id,
  label,
  className,
  value,
  names,
  onChange,
  onPick,
  onBlur,
}: {
  id: string;
  label: string;
  className: string;
  value: string;
  names: { name: string; hint?: string }[];
  onChange: (text: string) => void;
  onPick: (name: string) => void;
  onBlur: () => void;
}) {
  const list = useId();
  const field = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const place = useFieldPlace(field, open);
  const found = matching(
    names.map((n) => ({ key: n.name, label: n.name, hint: n.hint })),
    value,
  );
  const shown = open && found.length > 0 && !(found.length === 1 && found[0].label === value);
  const pick = (name: string) => {
    setOpen(false);
    onPick(name);
  };

  return (
    <>
      <input
        ref={field}
        id={id}
        data-name
        role="combobox"
        aria-expanded={shown}
        aria-controls={list}
        aria-activedescendant={shown && found[active] ? `${list}-${active}` : undefined}
        autoComplete="off"
        className={className}
        value={value}
        onClick={() => setOpen(true)}
        onChange={(event) => {
          onChange(event.target.value);
          setActive(-1);
          setOpen(true);
        }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            setOpen(true);
            setActive((k) => Math.max(0, Math.min(found.length - 1, k + (event.key === 'ArrowDown' ? 1 : -1))));
          } else if (event.key === 'Enter') {
            event.preventDefault();
            if (shown && found[active]) {
              pick(found[active].key);
            } else {
              event.currentTarget.blur();
            }
          } else if (event.key === 'Escape') {
            setOpen(false);
          }
        }}
        onBlur={() => {
          setOpen(false);
          onBlur();
        }}
      />
      {shown && place && <OptionList id={list} label={label} place={place} options={found} active={active} onPick={pick} onActive={setActive} />}
    </>
  );
}
