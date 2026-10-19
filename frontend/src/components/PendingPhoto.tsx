import React, { useCallback, useState } from "react";
import { Platform } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import * as FileSystem from "expo-file-system/legacy";
import { useAuth } from "@/src/auth";
import { storage } from "@/src/utils/storage";
import { CaptureDraft, DRAFT_KEY } from "@/src/capture-workflow";
import { Button, Card, ConfirmSheet, Txt, useToast } from "@/src/ui";
export function PendingPhoto() {
  const { user } = useAuth(), router = useRouter(), toast = useToast();
  const [draft,setDraft]=useState<CaptureDraft | null>(null);
  const [confirm,setConfirm]=useState(false), [busy,setBusy]=useState(false);
  useFocusEffect(useCallback(()=>{
    let alive=true;
    storage.getItem(`${DRAFT_KEY}:${user?.id}`,"").then(raw=>{
      if(!alive)return;
      if(!raw){setDraft(null);return;}
      try { const d=JSON.parse(raw); if(d.userId===user?.id && d.target.taskId)setDraft(d); }
      catch { /* Leave invalid draft untouched for support. */ }
    });
    return()=>{alive=false;};
  },[user]));
  const discard=async()=>{
    if(!draft || busy)return;
    setBusy(true);
    try {
      if(Platform.OS!=="web") for(const a of draft.assets) if(a.uri.startsWith(`${FileSystem.documentDirectory}capture-drafts/`)) await FileSystem.deleteAsync(a.uri,{idempotent:true});
      if(!(await storage.removeItem(`${DRAFT_KEY}:${user?.id}`)))throw Error("Could not remove this draft. Try again.");
      setDraft(null);setConfirm(false);toast("Pending attachment discarded");
    }catch(e:any){toast(e.message,"error");}finally{setBusy(false);}
  };
  return draft ? <Card><Txt v="subtitle">Photo waiting to be saved</Txt><Txt>{draft.target.label}</Txt>
    <Button title="Return to original task" onPress={()=>router.push(`/cleaning/${draft.target.taskId}`)} />
    <Txt v="caption">If the task was reassigned or is no longer available, you can discard this pending attachment to continue.</Txt>
    <Button title="Discard pending attachment" variant="ghost" onPress={()=>setConfirm(true)} />
    <ConfirmSheet visible={confirm} title="Discard pending attachment?" message="It will not be attached to any task. An already uploaded copy may remain in storage until cleanup." confirmLabel="Discard attachment" loading={busy} onConfirm={discard} onClose={()=>{if(!busy)setConfirm(false);}} />
  </Card> : null;
}
