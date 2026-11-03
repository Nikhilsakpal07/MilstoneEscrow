"use client";

import React from "react";
import { PayPalScriptProvider } from "@paypal/react-paypal-js";

interface ProvidersProps {
  children: React.ReactNode;
}

export default function Providers({ children }: ProvidersProps) {
  const clientId =
    process.env.NEXT_PUBLIC_PAYPAL_CLIENT_ID ||
    "BAAi_EO1kDZa0DaC9riRapXCd2FkezkocQRnjIvgsX0xZCgeoRk0D0yb-tGw5fXI5yQXiFxEM1eFON9xgk";

  const initialOptions = {
    clientId,
    currency: "USD",
    intent: "authorize",
  };

  return (
    <PayPalScriptProvider options={initialOptions}>
      {children}
    </PayPalScriptProvider>
  );
}
