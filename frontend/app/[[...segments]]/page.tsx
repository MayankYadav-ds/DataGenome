import Product from "../../components/Product";
export const dynamic = "force-dynamic";
export default async function Page({
  params,
}: {
  params: Promise<{ segments?: string[] }>;
}) {
  const { segments = [] } = await params;
  return <Product segments={segments} />;
}
