import { toast } from "sonner";

export const showError = (message: string, error?: unknown) => {
  if (error) console.error(message, error);
  toast.error(message);
};

export const showSuccess = (message: string) => toast.success(message);
