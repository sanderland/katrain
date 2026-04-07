import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardActionArea from '@mui/material/CardActionArea';
import CircularProgress from '@mui/material/CircularProgress';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import { TutorialAPI } from '../../api/tutorialApi';
import type { TutorialCategory } from '../../../types/tutorial';

export default function TutorialLandingPage() {
  const navigate = useNavigate();
  const [categories, setCategories] = useState<TutorialCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    TutorialAPI.getCategories()
      .then(setCategories)
      .catch(e => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  if (loading) return <Box display="flex" justifyContent="center" p={4}><CircularProgress /></Box>;
  if (error) return <Box p={3}><Alert severity="error">{error} <Button onClick={load}>重试</Button></Alert></Box>;

  return (
    <Box p={3}>
      <Typography variant="h5" gutterBottom>教程</Typography>
      <Typography variant="body2" color="text.secondary" gutterBottom>选择一个学习阶段开始学习</Typography>
      <Box display="flex" flexWrap="wrap" gap={2} mt={1}>
        {categories.map(cat => (
          <Box key={cat.slug} sx={{ flex: '1 1 260px', maxWidth: 360 }}>
            <Card>
              <CardActionArea onClick={() => navigate(`/galaxy/tutorials/${cat.slug}`)}>
                <CardContent>
                  <Typography variant="h6">{cat.title}</Typography>
                  <Typography variant="body2" color="text.secondary">{cat.summary}</Typography>
                  <Typography variant="caption" color="text.secondary" mt={1} display="block">
                    {cat.book_count} 本书
                  </Typography>
                </CardContent>
              </CardActionArea>
            </Card>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
