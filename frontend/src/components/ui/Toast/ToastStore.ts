import { create } from "zustand";

type ToastTone = "success" | "error" | "warning" | "info";

type ToastItem = {
  id: string;
  tone: ToastTone;
  title: string;
  description?: string;
};

type ToastState = {
  items: ToastItem[];
  push: (toast: Omit<ToastItem, "id">) => void;
  remove: (id: string) => void;
};

let counter = 0;

export const useToastStore = create<ToastState>((set) => ({
  items: [],
  push: (toast) => {
    const id = `toast-${++counter}`;
    set((s) => ({ items: [...s.items, { ...toast, id }] }));
    setTimeout(() => {
      set((s) => ({ items: s.items.filter((t) => t.id !== id) }));
    }, 5000);
  },
  remove: (id) =>
    set((s) => ({ items: s.items.filter((t) => t.id !== id) })),
}));
