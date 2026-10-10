import { Redirect } from "expo-router";
import { useAuth } from "@/src/auth";

export default function Index() {
  const { user } = useAuth();
  if (!user) return <Redirect href="/login" />;
  return <Redirect href={user.role === "admin" ? "/(admin)" : user.role === "owner" ? "/owner" : "/cleaning"} />;
}
