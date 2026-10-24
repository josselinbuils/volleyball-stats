import { TooltipProvider } from '@/components/ui/tooltip';
import { ActionsTable } from '@/components/ActionsTable';
import { CourtChart } from '@/components/CourtChart/CourtChart';
import { Header } from '@/components/Header';
import { RallyCharts } from '@/components/RallyCharts/RallyCharts';
import { Watch } from '@/components/Watch/Watch';
import { PlayerProvider } from '@/lib/player';

export function App() {
  return (
    <TooltipProvider delayDuration={200}>
      <PlayerProvider>
        <main className="mx-auto grid w-full max-w-6xl gap-5 px-4 pt-8 pb-16 max-sm:pt-5 max-sm:gap-4">
          <Header />
          <ActionsTable />
          <Watch />
          <CourtChart />
          <RallyCharts />
        </main>
      </PlayerProvider>
    </TooltipProvider>
  );
}
