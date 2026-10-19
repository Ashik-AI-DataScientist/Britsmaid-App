import React, { useEffect, useState } from "react";
import { useRouter } from "expo-router";
import { useAuth } from "@/src/auth";
import { storage } from "@/src/utils/storage";
import { CaptureDraft, DRAFT_KEY } from "@/src/capture-workflow";
import { Button, Card, Txt } from "@/src/ui";
export function PendingPhoto() {
  const { user } = useAuth(), router = useRouter();
  const [draft,setDraft]=useState<CaptureDraft | null>(null);
  useEffect(()=>{ let alive=true; storage.getItem(`${DRAFT_KEY}:${user?.id}`,"").then(raw=>{if(!alive || !raw)return;try { const d=JSON.parse(raw); if(d.userId===user?.id && d.target.taskId)setDraft(d); }catch { /* Leave invalid draft untouched for support. */ }}); return()=>{alive=false;}; },[user?.id]);
  return draft ? <Card><Txt v="subtitle">Photo waiting to be saved</Txt><Txt>{draft.target.label}</Txt><Button title="Return to original task" onPress={()=>router.push(`/cleaning/${draft.target.taskId}`)} /></Card> : null;
}
