import { useEffect } from 'react';
import { TooltipProvider } from '@/components/ui/tooltip';
import { BrandBar } from '@/components/BrandBar';
import { CourtChart } from '@/components/CourtChart/CourtChart';
import { Header } from '@/components/Header/Header';
import { PlayersTable } from '@/components/Stats/PlayersTable';
import { RallyCharts } from '@/components/RallyCharts/RallyCharts';
import { Watch } from '@/components/Watch/Watch';
import { PlayerProvider } from '@/lib/player';
import { match } from '@/lib/match';
import { loadPlayers } from '@/lib/players';
import { SetProvider } from '@/lib/sets';

export function App() {
  // The players' positions start loading right after the first paint: well before anyone presses
  // play, without delaying that paint.
  useEffect(() => {
    let timer = 0;
    const frame = requestAnimationFrame(() => {
      timer = window.setTimeout(loadPlayers);
    });
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(timer);
    };
  }, []);

  return (
    <TooltipProvider delayDuration={200}>
      <PlayerProvider>
        <SetProvider>
          <BrandBar brand={match.brand} />
          <main className="mx-auto grid w-full max-w-6xl gap-5 px-4 pt-8 pb-16 max-sm:pt-5 max-sm:gap-4">
            <Header />
            <PlayersTable />
            <Watch />
            <CourtChart />
            <RallyCharts />
          </main>
        </SetProvider>
      </PlayerProvider>
    </TooltipProvider>
  );
}
