import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import CircularProgress from '@mui/material/CircularProgress';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Dialog from '@mui/material/Dialog';
import DialogContent from '@mui/material/DialogContent';
import Accordion from '@mui/material/Accordion';
import AccordionSummary from '@mui/material/AccordionSummary';
import AccordionDetails from '@mui/material/AccordionDetails';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import PlayCircleOutlineIcon from '@mui/icons-material/PlayCircleOutline';
import CloseIcon from '@mui/icons-material/Close';
import { TutorialAPI } from '../../api/tutorialApi';
import type { TutorialBookDetail, TutorialSection } from '../../../types/tutorial';

export default function TutorialBookDetailPage() {
  const { bookId } = useParams<{ bookId: string }>();
  const navigate = useNavigate();
  const [book, setBook] = useState<TutorialBookDetail | null>(null);
  const [sections, setSections] = useState<Record<number, TutorialSection[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [videoDialogUrl, setVideoDialogUrl] = useState<string | null>(null);
  const [sectionVideos, setSectionVideos] = useState<Record<number, boolean>>({});

  const checkSectionVideo = useCallback(async (sectionId: number, slug: string) => {
    const url = TutorialAPI.assetUrl(`tutorial_assets/${slug}/video/section_${sectionId}.mp4`);
    try {
      // Use range request to avoid downloading the full file (HEAD not supported by asset endpoint)
      const resp = await fetch(url, { method: 'GET', headers: { Range: 'bytes=0-0' } });
      return resp.ok || resp.status === 206;
    } catch {
      return false;
    }
  }, []);

  const load = () => {
    if (!bookId) return;
    setLoading(true);
    setError(null);
    TutorialAPI.getBook(Number(bookId))
      .then(async (b) => {
        setBook(b);
        // Load sections for each chapter
        const sectionMap: Record<number, TutorialSection[]> = {};
        await Promise.all(
          b.chapters.map(async (ch) => {
            const secs = await TutorialAPI.getSections(ch.id);
            sectionMap[ch.id] = secs;
          })
        );
        setSections(sectionMap);
        // Check which sections have videos
        const allSections = Object.values(sectionMap).flat();
        const videoChecks = await Promise.all(
          allSections.map(async (sec) => [sec.id, await checkSectionVideo(sec.id, b.slug)] as const)
        );
        setSectionVideos(Object.fromEntries(videoChecks));
      })
      .catch(e => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [bookId]);

  if (loading) return <Box display="flex" justifyContent="center" p={4}><CircularProgress /></Box>;
  if (error) return <Box p={3}><Alert severity="error">{error} <Button onClick={load}>重试</Button></Alert></Box>;
  if (!book) return <Box p={3}><Typography>书籍不存在</Typography></Box>;

  return (
    <Box p={3}>
      <Button size="small" onClick={() => navigate(`/galaxy/tutorials/${book.category}`)} sx={{ mb: 1 }}>← 返回</Button>
      <Typography variant="h5" gutterBottom>{book.title}</Typography>
      {book.author && <Typography variant="body2" color="text.secondary" gutterBottom>{book.author}</Typography>}

      {book.chapters.map(ch => (
        <Accordion key={ch.id} defaultExpanded={book.chapters.length <= 3}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography>{ch.chapter_number} {ch.title}</Typography>
            <Typography variant="caption" color="text.secondary" sx={{ ml: 2 }}>
              {ch.section_count} 节
            </Typography>
          </AccordionSummary>
          <AccordionDetails sx={{ p: 0 }}>
            <List dense disablePadding>
              {(sections[ch.id] ?? []).map(sec => (
                <ListItemButton
                  key={sec.id}
                  onClick={() => navigate(`/galaxy/tutorials/section/${sec.id}`)}
                  sx={{ pl: 1 }}
                >
                  {/* Play button — fixed width for alignment, visible only when video exists */}
                  <Box sx={{ width: 36, minWidth: 36, mr: 0.5, display: 'flex', justifyContent: 'center' }}>
                    {sectionVideos[sec.id] ? (
                      <IconButton
                        size="small"
                        onClick={(e) => {
                          e.stopPropagation();
                          setVideoDialogUrl(
                            TutorialAPI.assetUrl(`tutorial_assets/${book.slug}/video/section_${sec.id}.mp4`)
                          );
                        }}
                        title="播放视频"
                      >
                        <PlayCircleOutlineIcon />
                      </IconButton>
                    ) : null}
                  </Box>
                  <ListItemText
                    primary={`${sec.section_number}. ${sec.title}`}
                    secondary={`${sec.figure_count} 个变化图`}
                  />
                </ListItemButton>
              ))}
            </List>
          </AccordionDetails>
        </Accordion>
      ))}

      {/* Fullscreen video dialog */}
      <Dialog
        open={!!videoDialogUrl}
        onClose={() => setVideoDialogUrl(null)}
        maxWidth={false}
        fullScreen
        PaperProps={{ sx: { bgcolor: '#000' } }}
      >
        <IconButton
          onClick={() => setVideoDialogUrl(null)}
          sx={{ position: 'absolute', top: 8, right: 8, color: '#fff', zIndex: 1 }}
        >
          <CloseIcon />
        </IconButton>
        <DialogContent sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', p: 0 }}>
          {videoDialogUrl && (
            <video
              controls
              autoPlay
              preload="none"
              style={{ maxWidth: '100%', maxHeight: '100%' }}
              src={videoDialogUrl}
            />
          )}
        </DialogContent>
      </Dialog>
    </Box>
  );
}
