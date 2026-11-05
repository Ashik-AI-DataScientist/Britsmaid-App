import React, { useState } from 'react';
import { View } from 'react-native';
import { Button, Row, Txt } from '@/src/ui';
import { MediaThumb } from '@/src/components/MediaThumb';
import { inr } from '@/src/format';

export function ExpenseDetails({ item }: { item: any }) {
  const [open, setOpen] = useState(false);
  const [documents, setDocuments] = useState(false);
  const a = item.allocation;
  return <View style={{ gap: 8 }}>
    <Button small variant="ghost" title={`${item.title || (item.type === 'electricity' ? 'Electricity' : 'Expense')} · ${inr(item.amount)} · ${open ? 'Hide' : 'Details'}`} onPress={() => setOpen(!open)} />
    {open ? <View style={{ gap: 8 }}>
      <Txt>{item.notes || 'No note recorded'}</Txt>
      <Txt v="caption">{item.type === 'pre_split' ? 'Deducted before the revenue split' : a ? 'Allocated after the revenue split' : 'Original property expense rule'}</Txt>
      {a || item.owner_amount != null ? <>
        <Row label={`Owner${a ? ` (${a.owner_percent}%${a.manual ? ', adjusted' : ''})` : ''}`} value={inr(a?.owner_amount ?? item.owner_amount)} />
        <Row label={`Britsmaid${a ? ` (${a.britsmaid_percent}%${a.manual ? ', adjusted' : ''})` : ''}`} value={inr(a?.britsmaid_amount ?? item.britsmaid_amount)} />
      </> : null}
      {item.media_ids?.length ? <Button small variant="secondary" title={`${documents ? 'Hide' : 'View'} attachments (${item.media_ids.length})`} onPress={() => setDocuments(!documents)} /> : null}
      {documents ? <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>{(item.media_ids || []).map((id: string) => <MediaThumb key={id} id={id} kind="image" size={96} />)}</View> : null}
    </View> : null}
  </View>;
}
