import React, { useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/src/api';
import { Button, Card, Chip, ErrorState, Loading, Txt } from '@/src/ui';
import { DateField } from './DateField';
import { addDays, fmtShort, inr, monthShort, shiftMonth, todayISO } from '@/src/format';
import { spacing, useTheme } from '@/src/theme';

type Point = { period: string; gross: number; net: number; bookings: number };

export function RevenueInsights({ propertyId = '', month, onMonthPress }: { propertyId?: string; month: string; onMonthPress?: (month: string) => void }) {
  const { colors } = useTheme();
  const monthEnd = addDays(`${shiftMonth(month, 1)}-01`, -1);
  const dailyEnd = todayISO().slice(0, 7) === month ? todayISO() : monthEnd;
  const [preset, setPreset] = useState('6 months');
  const [start, setStart] = useState(`${shiftMonth(month, -5)}-01`);
  const [end, setEnd] = useState(monthEnd);
  const [interval, setInterval] = useState('month');
  const [metric, setMetric] = useState<'gross' | 'net'>('gross');
  const [selected, setSelected] = useState('');
  const [width, setWidth] = useState(300);
  const days = Math.round((Date.parse(end) - Date.parse(start)) / 86400000) + 1;
  const valid = Number.isFinite(days) && days > 0 && days <= 731 && (interval !== 'day' || days <= 93);
  const q = useQuery({ queryKey: ['revenue-insights', propertyId, start, end, interval], enabled: valid,
    queryFn: () => api.get(`/reports/insights?start=${start}&end=${end}&interval=${interval}&property_id=${propertyId}`) });
  const points: Point[] = q.data?.points ?? [];
  const chosen = points.find(point => point.period === selected) ?? points[points.length - 1];
  const low = Math.min(0, ...points.map(point => point[metric]));
  const high = Math.max(1, ...points.map(point => point[metric]));
  const plotWidth = Math.max(width - 65, points.length * 28, 180);
  const height = 180;
  const x = (index: number) => 12 + index * (plotWidth - 24) / Math.max(1, points.length - 1);
  const y = (value: number) => 8 + (high - value) / (high - low) * (height - 16);
  const choosePreset = (value: string) => {
    setPreset(value); setSelected('');
    if (value === 'Custom') return;
    const daily = value === '7 days' || value === '30 days';
    setEnd(daily ? dailyEnd : monthEnd);
    setInterval(daily ? 'day' : 'month');
    setStart(daily ? addDays(dailyEnd, value === '7 days' ? -6 : -29) : `${shiftMonth(month, value === '12 months' ? -11 : -5)}-01`);
  };
  const axisMoney = (value: number) => Math.abs(value) >= 100000 ? `₹${(value / 100000).toFixed(1)}L` : Math.abs(value) >= 1000 ? `₹${(value / 1000).toFixed(1)}K` : inr(value);
  const ticks = Math.min(points.length, Math.max(2, Math.floor(plotWidth / 90)));
  const tickIndexes = new Set(Array.from({ length: ticks }, (_, index) => Math.round(index * (points.length - 1) / Math.max(1, ticks - 1))));
  const label = (point: Point) => interval === 'day' ? fmtShort(point.period) : `${monthShort(point.period)} ${point.period.slice(2, 4)}`;
  return <Card testID="trend-card" style={{ gap: spacing.md }}>
    <Txt v="subtitle">Revenue insights</Txt>
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>{['7 days', '30 days', '6 months', '12 months', 'Custom'].map(value =>
      <Chip key={value} label={value} selected={preset === value} onPress={() => choosePreset(value)} />)}</View>
    {preset === 'Custom' ? <View style={{ gap: 12 }}>
      <DateField label="From" value={start} onChange={setStart} testID="insights-start" />
      <DateField label="To" value={end} onChange={setEnd} min={start} testID="insights-end" />
    </View> : null}
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
      <Chip label="By day" selected={interval === 'day'} onPress={() => setInterval('day')} />
      <Chip label="By month" selected={interval === 'month'} onPress={() => setInterval('month')} />
      <Chip label="Gross revenue" selected={metric === 'gross'} onPress={() => setMetric('gross')} />
      <Chip label="Net booking revenue" selected={metric === 'net'} onPress={() => setMetric('net')} />
    </View>
    {!valid ? <Txt>Choose up to 93 days for daily points, or two years for monthly points.</Txt> : q.isLoading ? <Loading /> : q.isError ? <ErrorState onRetry={q.refetch} /> : <>
      <Txt v="caption">{metric === 'gross' ? 'Gross revenue' : 'Net booking revenue'} · INR (₹)</Txt>
      <View onLayout={event => setWidth(event.nativeEvent.layout.width)} style={{ flexDirection: 'row', height: height + 42 }}>
        <View style={{ width: 65, height, justifyContent: 'space-between', paddingVertical: 4 }}>
          {[high, (high + low) / 2, low].map((value, index) => <Txt key={index} v="caption" numberOfLines={1}>{axisMoney(value)}</Txt>)}
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator contentContainerStyle={{ width: plotWidth }}>
          <View style={{ width: plotWidth, height: height + 34 }}>
            {[0, .5, 1].map(ratio => <View key={ratio} style={{ position: 'absolute', top: 8 + ratio * (height - 16), left: 0, right: 0, borderTopWidth: 1, borderColor: colors.divider }} />)}
            {points.slice(1).map((point, offset) => {
              const index = offset + 1, dx = x(index) - x(index - 1), dy = y(point[metric]) - y(points[index - 1][metric]);
              const length = Math.sqrt(dx * dx + dy * dy);
              return <View key={`line-${point.period}`} style={{ position: 'absolute', left: (x(index) + x(index - 1) - length) / 2,
                top: (y(point[metric]) + y(points[index - 1][metric])) / 2 - 1, width: length, height: 2,
                backgroundColor: colors.brandPrimary, transform: [{ rotate: `${Math.atan2(dy, dx)}rad` }] }} />;
            })}
            {points.map((point, index) => <Pressable key={point.period} accessibilityRole="button" accessibilityLabel={`${point.period}, ${inr(point[metric])}`}
              onPress={() => setSelected(point.period)} style={{ position: 'absolute', left: x(index) - 10, top: y(point[metric]) - 10, width: 20, height: 20, alignItems: 'center', justifyContent: 'center' }}>
              <View style={{ width: chosen?.period === point.period ? 10 : 6, height: chosen?.period === point.period ? 10 : 6, borderRadius: 5, backgroundColor: colors.brandPrimary }} />
            </Pressable>)}
            {points.filter((_, index) => tickIndexes.has(index)).map(point => {
              const index = points.indexOf(point);
              return <View key={`label-${point.period}`} style={{ position: 'absolute', top: height + 6, width: 72, left: Math.min(plotWidth - 72, Math.max(0, x(index) - 36)) }}><Txt v="caption" numberOfLines={1}>{label(point)}</Txt></View>;
            })}
          </View>
        </ScrollView>
      </View>
      <Txt v="caption">{start} to {end} · {interval === 'day' ? 'Date' : 'Month'} →</Txt>
      {chosen ? <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 16 }}>
        <Txt>{chosen.period}</Txt><Txt>Gross {inr(chosen.gross)}</Txt><Txt>Net {inr(chosen.net)}</Txt><Txt>{chosen.bookings} bookings</Txt>
      </View> : <Txt>No revenue in this period.</Txt>}
      {chosen && interval === "month" && onMonthPress ? <Button small title="Open selected month statement" variant="secondary" onPress={() => onMonthPress(chosen.period)} /> : null}
      <Txt v="caption">{q.data?.basis}</Txt>
    </>}
  </Card>;
}
