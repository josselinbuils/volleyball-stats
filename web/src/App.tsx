import { VideoChoice } from '@/components/VideoChoice';
import { ClubBar } from '@/components/ClubBar';
import { Coach } from '@/components/Coach/Coach';
import { CourtChart } from '@/components/CourtChart/CourtChart';
import { Header } from '@/components/Header/Header';
import { MyMatch } from '@/components/MyMatch/MyMatch';
import { PlayersTable } from '@/components/Stats/PlayersTable';
import { RallyCharts } from '@/components/RallyCharts/RallyCharts';
import { Story } from '@/components/Story/Story';
import { Trophies } from '@/components/Trophies/Trophies';
import { Watch } from '@/components/Watch/Watch';
import { PlayerProvider } from '@/lib/player';
import { match } from '@/lib/match';
import { SetProvider } from '@/lib/sets';

export function App() {
  return (
    <PlayerProvider>
      <SetProvider>
        <ClubBar club={match.club} />
        <VideoChoice />
        <main className="mx-auto grid w-full max-w-6xl gap-5 px-4 pt-8 pb-16 max-sm:pt-5 max-sm:gap-4">
          <Header />
          <Story />
          <PlayersTable />
          <Watch />
          <CourtChart />
          <MyMatch />
          <Trophies />
          <Coach />
          <RallyCharts />
        </main>
      </SetProvider>
    </PlayerProvider>
  );
}
